"""
services/code_health.py

Salud del código de un proyecto analizado:

- Código muerto: funciones/métodos definidos que nadie referencia en el proyecto.
- Código duplicado: bloques de líneas idénticos (normalizados) repetidos en uno o
  varios archivos.
- Mapa de calor de complejidad: puntuación de "riesgo" 0-100 por archivo (sin archivos de prueba).

Solo usa la librería estándar, así que también se puede ejecutar fuera del
servidor (por ejemplo desde la GitHub Action, ver scripts/autodocs_ci.py).

Notas de precisión
------------------
* El código muerto se detecta por nombre: una función se marca como "sin uso" si
  su nombre solo aparece en su propia definición. Es una heurística conservadora
  (cualquier mención en cadenas, comentarios o plantillas cuenta como uso), por lo
  que puede dejar pasar código muerto, pero rara vez marcará código vivo.
* En Python se usa el AST para ignorar funciones decoradas (rutas, fixtures,
  tareas...), métodos de clases con herencia (hooks de frameworks), dunders y tests.
* En lenguajes orientados a objetos con interfaces (Java, C#, Kotlin, Swift, Scala)
  la detección por nombre es poco fiable, así que no se reporta código muerto.
"""
import ast
import hashlib
import os
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from services.analyzer import ProjectAnalyzer

# ── Configuración ────────────────────────────────────────────────────────────
IGNORE_DIRS = set(ProjectAnalyzer.IGNORE_DIRS)
CODE_EXTENSIONS = {
    ext for ext, lang in ProjectAnalyzer.LANGUAGE_EXTENSIONS.items()
    if lang in ProjectAnalyzer.DEEP_ANALYSIS_LANGS
}
# Archivos que no se analizan pero sí cuentan como "referencias" (p. ej. onclick="fn()")
REFERENCE_ONLY_EXTENSIONS = {
    '.html', '.htm', '.vue', '.svelte', '.j2', '.jinja', '.jinja2',
    '.yaml', '.yml', '.toml', '.cfg', '.ini', '.json',
}
HASH_COMMENT_EXTENSIONS = {'.py', '.rb', '.ex', '.exs', '.php'}
# Lenguajes en los que la detección de código muerto por nombre es razonable
DEAD_CODE_EXTENSIONS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.rb', '.php',
    '.c', '.cc', '.cpp', '.cxx', '.h', '.ex', '.exs',
}

MAX_FILES = 2000
MAX_FILE_BYTES = 512 * 1024
DUP_WINDOW = 6            # nº de líneas significativas consecutivas que forman un bloque
DUP_MIN_CHARS = 120       # caracteres mínimos de una ventana para no contar boilerplate
MAX_OCC_PER_HASH = 8
MAX_DUP_GROUPS = 25
MAX_DEAD = 100
MAX_HEATMAP = 80

ENTRYPOINT_NAMES = {
    'main', 'setup', 'teardown', 'setUp', 'tearDown', 'run', 'handler',
    'lambda_handler', 'index', 'create_app', 'app', 'application', 'wsgi',
    'default', 'constructor', 'init', 'initialize', 'render', 'configure',
}
IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
IMPORT_LINE_RE = re.compile(
    r'^(import |from \S+ import |#include|using |require\(|require |package |use |export \{|export \*)'
)
BRANCH_RE = re.compile(
    r'\b(?:if|elif|else\s+if|for|foreach|while|case|catch|switch|when|rescue|unless)\b|&&|\|\||\?\s'
)


# ── Utilidades ───────────────────────────────────────────────────────────────
def _is_test_path(rel: str) -> bool:
    low = rel.lower().replace('\\', '/')
    parts = low.split('/')
    name = parts[-1]
    return (
        any(p in ('test', 'tests', '__tests__', 'spec', 'specs') for p in parts[:-1])
        or name.startswith('test_') or name.startswith('conftest')
        or name.endswith(('_test.py', '.test.js', '.test.ts', '.spec.js', '.spec.ts',
                          '.test.jsx', '.test.tsx', '_test.go'))
    )


def _iter_files(root: Path):
    """Recorre el proyecto de forma determinista respetando carpetas ignoradas."""
    count = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            if ext not in CODE_EXTENSIONS and ext not in REFERENCE_ONLY_EXTENSIONS:
                continue
            full = Path(dirpath) / fname
            try:
                if full.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rel = str(full.relative_to(root)).replace(os.sep, '/')
            yield rel, full, ext
            count += 1
            if count >= MAX_FILES:
                return


def _is_comment(line: str, ext: str) -> bool:
    if line.startswith(('//', '/*', '*', '*/')):
        return True
    return ext in HASH_COMMENT_EXTENSIONS and line.startswith('#')


def _python_defs(tree, rel: str):
    """Extrae definiciones de funciones con el contexto necesario para filtrar falsos positivos."""
    defs = []

    def visit(node, cls=None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, child)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append({
                    "name": child.name, "file": rel, "line": child.lineno,
                    "decorated": bool(child.decorator_list),
                    "in_class": cls is not None,
                    "class_has_bases": bool(cls.bases) if cls is not None else False,
                })
                visit(child, None)
            else:
                visit(child, cls)

    visit(tree)
    return defs


# ── Escaneo de archivos (una sola pasada) ────────────────────────────────────
def _scan_project(root: Path, window: int):
    files = []              # archivos de código con su información
    tokens = Counter()      # apariciones de cada identificador en todo el proyecto
    python_defs = []

    for rel, full, ext in _iter_files(root):
        try:
            text = full.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        tokens.update(IDENT_RE.findall(text))
        if ext not in CODE_EXTENSIONS:
            continue

        norm_lines, linenos = [], []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = re.sub(r'\s+', ' ', raw.strip())
            if len(line) <= 3 or _is_comment(line, ext):
                continue
            norm_lines.append(line)
            linenos.append(lineno)

        hashes = []
        for i in range(max(len(norm_lines) - window + 1, 0)):
            chunk = norm_lines[i:i + window]
            joined = '\n'.join(chunk)
            imports = sum(1 for ln in chunk if IMPORT_LINE_RE.match(ln))
            if len(joined) < DUP_MIN_CHARS or imports > window // 2:
                hashes.append(None)
            else:
                hashes.append(hashlib.md5(joined.encode('utf-8')).hexdigest()[:16])

        info = {
            "rel": rel, "ext": ext, "loc": len(norm_lines),
            "branches": len(BRANCH_RE.findall(text)) if ext != '.py' else 0,
            "linenos": linenos, "hashes": hashes,
        }
        files.append(info)

        if ext == '.py':
            try:
                python_defs.extend(_python_defs(ast.parse(text), rel))
            except (SyntaxError, ValueError, RecursionError):
                pass

    return files, tokens, python_defs


# ── 1. Código muerto ─────────────────────────────────────────────────────────
def _find_dead_code(tokens: Counter, python_defs: list, results: dict):
    candidates = []
    def_count = Counter()

    for d in python_defs:
        def_count[d["name"]] += 1
        name = d["name"]
        if (d["decorated"] or (d["in_class"] and d["class_has_bases"])
                or (name.startswith('__') and name.endswith('__'))
                or name in ENTRYPOINT_NAMES or name.lower().startswith('test')
                or _is_test_path(d["file"]) or len(name) <= 2):
            continue
        candidates.append({
            "name": name, "file": d["file"], "line": d["line"],
            "kind": "método" if d["in_class"] else "función", "confidence": "alta",
        })

    for fn in results.get("functions", []) or []:
        rel = str(fn.get("file", "")).replace(os.sep, '/')
        ext = Path(rel).suffix.lower()
        if ext == '.py' or not rel:
            continue
        name = fn.get("name", "")
        def_count[name] += 1
        if (ext not in DEAD_CODE_EXTENSIONS or not name or len(name) <= 2
                or name in ENTRYPOINT_NAMES or name.lower().startswith('test')
                or _is_test_path(rel)):
            continue
        candidates.append({
            "name": name, "file": rel, "line": fn.get("line") or 0,
            "kind": "función", "confidence": "media",
        })

    dead = []
    for c in candidates:
        if tokens.get(c["name"], 0) <= def_count[c["name"]]:
            c["reason"] = f"El nombre `{c['name']}` no aparece en ningún otro lugar del proyecto."
            dead.append(c)
    dead.sort(key=lambda c: (0 if c["confidence"] == "alta" else 1, c["file"], c["line"]))
    return dead


# ── 2. Código duplicado ──────────────────────────────────────────────────────
def _find_duplicates(files: list, window: int, root: Path):
    by_rel = {f["rel"]: f for f in files}
    index = defaultdict(list)
    for f in files:
        for i, h in enumerate(f["hashes"]):
            if h is not None:
                index[h].append((f["rel"], i))

    covered = defaultdict(list)
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for occs in index.values():
        if len(occs) < 2:
            continue
        occs = sorted(occs)[:MAX_OCC_PER_HASH]
        for (fa, ia), (fb, ib) in combinations(occs, 2):
            key = (fa, fb, ib - ia)
            if any(s <= ia <= e for s, e in covered[key]):
                continue
            ha, hb = by_rel[fa]["hashes"], by_rel[fb]["hashes"]
            back = 0
            while (ia - back - 1 >= 0 and ib - back - 1 >= 0
                   and ha[ia - back - 1] is not None
                   and ha[ia - back - 1] == hb[ib - back - 1]):
                back += 1
            fwd = 0
            while (ia + fwd + 1 < len(ha) and ib + fwd + 1 < len(hb)
                   and ha[ia + fwd + 1] is not None
                   and ha[ia + fwd + 1] == hb[ib + fwd + 1]):
                fwd += 1
            covered[key].append((ia - back, ia + fwd))
            a_start, a_end = ia - back, ia + fwd + window - 1
            b_start, b_end = ib - back, ib + fwd + window - 1
            if fa == fb and b_start <= a_end:      # bloques solapados: patrón repetitivo
                continue
            union((fa, a_start, a_end), (fb, b_start, b_end))

    # Unir bloques que se solapan dentro del mismo archivo (mismo fragmento visto desde
    # distintas parejas) para no reportar el mismo duplicado varias veces.
    nodes_by_file = defaultdict(list)
    for node in list(parent):
        nodes_by_file[node[0]].append(node)
    for nodes in nodes_by_file.values():
        nodes.sort(key=lambda n: (n[1], n[2]))
        furthest = nodes[0]
        for node in nodes[1:]:
            if node[1] <= furthest[2]:
                union(furthest, node)
            if node[2] > furthest[2]:
                furthest = node

    groups = defaultdict(list)
    for node in list(parent):
        groups[find(node)].append(node)

    result = []
    for nodes in groups.values():
        per_file = defaultdict(list)
        for f, s, e in nodes:
            per_file[f].append([s, e])
        occurrences = []
        for f, ranges in per_file.items():
            ranges.sort()
            merged = []
            for s, e in ranges:
                if merged and s <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], e)
                else:
                    merged.append([s, e])
            for s, e in merged:
                linenos = by_rel[f]["linenos"]
                occurrences.append({
                    "file": f, "start_line": linenos[s], "end_line": linenos[e],
                    "_size": e - s + 1,
                })
        if len(occurrences) < 2:
            continue
        occurrences.sort(key=lambda o: (o["file"], o["start_line"]))
        lines = min(o["_size"] for o in occurrences)
        for o in occurrences:
            del o["_size"]
        result.append({"lines": lines, "occurrences": occurrences})

    result.sort(key=lambda g: (-(g["lines"] * len(g["occurrences"])),
                               g["occurrences"][0]["file"], g["occurrences"][0]["start_line"]))
    result = result[:MAX_DUP_GROUPS]

    for g in result:
        first = g["occurrences"][0]
        try:
            src = (root / first["file"]).read_text(encoding='utf-8', errors='ignore').splitlines()
            snippet = src[first["start_line"] - 1:min(first["end_line"], first["start_line"] + 7)]
            g["snippet"] = '\n'.join(s.rstrip()[:140] for s in snippet)
        except OSError:
            g["snippet"] = ""
    return result


# ── 3. Mapa de calor de complejidad ──────────────────────────────────────────
def _heat_level(score: int) -> str:
    if score >= 75:
        return "crítico"
    if score >= 50:
        return "alto"
    if score >= 25:
        return "medio"
    return "bajo"


def _build_heatmap(files: list, results: dict):
    by_file = defaultdict(list)
    for fn in results.get("functions", []) or []:
        by_file[str(fn.get("file", "")).replace(os.sep, '/')].append(fn)

    entries = []
    for f in files:
        if _is_test_path(f["rel"]):      # los tests largos no son accionables: se excluyen del ranking
            continue
        funcs = by_file.get(f["rel"], [])
        nfuncs = len(funcs)
        if f["ext"] == '.py':
            total = sum(int(fn.get("complexity", 1) or 1) for fn in funcs)
            max_cx = max((int(fn.get("complexity", 1) or 1) for fn in funcs), default=0)
            source = "ast"
            max_component = max_cx
        else:
            total = f["branches"]
            max_cx = None
            source = "estimado"
            max_component = total / max(nfuncs, 1) * 1.5
        score = round(
            min(total, 100) / 100 * 50
            + min(max_component, 25) / 25 * 35
            + min(f["loc"], 1000) / 1000 * 15
        )
        score = max(0, min(100, score))
        entries.append({
            "file": f["rel"], "language": ProjectAnalyzer.LANGUAGE_EXTENSIONS.get(f["ext"], "other"),
            "loc": f["loc"], "functions": nfuncs, "total_complexity": total,
            "max_complexity": max_cx, "score": score, "level": _heat_level(score),
            "source": source,
        })
    entries.sort(key=lambda e: (-e["score"], e["file"]))
    return entries


# ── API pública ──────────────────────────────────────────────────────────────
def analyze_code_health(project_path, results: dict = None, window: int = DUP_WINDOW) -> dict:
    """
    Calcula código muerto, duplicados y mapa de calor de un proyecto.

    Args:
        project_path: carpeta raíz del proyecto.
        results: salida de ProjectAnalyzer.analyze() (se usa para funciones y complejidad).
        window: nº de líneas consecutivas que definen un bloque duplicado.
    """
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError(f"La ruta del proyecto no es un directorio: {project_path}")
    results = results or {}

    files, tokens, python_defs = _scan_project(root, window)
    dead = _find_dead_code(tokens, python_defs, results)
    dup_groups = _find_duplicates(files, window, root)
    heat = _build_heatmap(files, results)

    duplicated_lines = sum(g["lines"] * (len(g["occurrences"]) - 1) for g in dup_groups)
    hot_files = sum(1 for e in heat if e["score"] >= 50)
    avg_heat = round(sum(e["score"] for e in heat) / len(heat), 1) if heat else 0

    return {
        "version": 1,
        "dead_code": {
            "count": len(dead),
            "items": dead[:MAX_DEAD],
            "truncated": len(dead) > MAX_DEAD,
            "note": ("Detección por nombre: revisa cada caso antes de borrar. "
                     "No se analizan Java, C#, Kotlin, Swift ni Scala."),
        },
        "duplicates": {
            "groups": len(dup_groups),
            "duplicated_lines": duplicated_lines,
            "window": window,
            "items": dup_groups,
        },
        "heatmap": {
            "files": heat[:MAX_HEATMAP],
            "total_files": len(heat),
            "summary": {"avg_score": avg_heat, "hot_files": hot_files},
        },
        "summary": {
            "dead_code": len(dead),
            "duplicate_groups": len(dup_groups),
            "duplicated_lines": duplicated_lines,
            "hot_files": hot_files,
            "avg_heat": avg_heat,
        },
    }
