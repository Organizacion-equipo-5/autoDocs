#services/analyzer.py
import os
import ast
import re
from pathlib import Path
from collections import defaultdict


class ProjectAnalyzer:
    """
    Analiza un proyecto completo y extrae información estructural y técnica.

    Este script se usa para:
    - recorrer el árbol de archivos del proyecto
    - detectar el lenguaje dominante
    - extraer funciones, clases y endpoints
    - calcular métricas de calidad

    Los resultados se consumen luego por DocGenerator para generar la documentación.
    """

    LANGUAGE_EXTENSIONS = {
        # Web / scripting
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.jsx': 'React (JSX)', '.tsx': 'React (TSX)',
        '.php': 'PHP', '.rb': 'Ruby', '.pl': 'Perl', '.lua': 'Lua',
        # Systems
        '.c': 'C', '.h': 'C/C++ Header', '.cpp': 'C++', '.cc': 'C++', '.cxx': 'C++',
        '.cs': 'C#', '.rs': 'Rust', '.go': 'Go', '.zig': 'Zig', '.nim': 'Nim',
        # JVM
        '.java': 'Java', '.kt': 'Kotlin', '.kts': 'Kotlin',
        '.scala': 'Scala', '.groovy': 'Groovy', '.clj': 'Clojure',
        # Mobile
        '.swift': 'Swift', '.m': 'Objective-C', '.dart': 'Dart',
        # Functional
        '.hs': 'Haskell', '.elm': 'Elm',
        '.ex': 'Elixir', '.exs': 'Elixir', '.erl': 'Erlang',
        '.ml': 'OCaml', '.fs': 'F#', '.fsx': 'F#',
        # Data / scientific
        '.r': 'R', '.jl': 'Julia',
        '.sql': 'SQL', '.psql': 'SQL',
        # Shell
        '.sh': 'Shell', '.bash': 'Bash', '.zsh': 'Zsh',
        '.ps1': 'PowerShell', '.bat': 'Batch',
        # Frontend / markup
        '.html': 'HTML', '.htm': 'HTML', '.css': 'CSS',
        '.scss': 'SCSS', '.sass': 'Sass', '.less': 'LESS',
        '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
        '.json': 'JSON', '.toml': 'TOML', '.ini': 'INI',
        # Infra
        '.tf': 'Terraform', '.hcl': 'HCL',
        # Other
        '.proto': 'Protobuf', '.graphql': 'GraphQL', '.gql': 'GraphQL',
        '.sol': 'Solidity', '.coffee': 'CoffeeScript',
        '.v': 'Verilog', '.sv': 'SystemVerilog',
    }

    DEEP_ANALYSIS_LANGS = {
        'Python', 'JavaScript', 'TypeScript', 'React (JSX)', 'React (TSX)',
        'Java', 'PHP', 'Ruby', 'Go', 'Rust', 'C#', 'Kotlin', 'Swift',
        'C', 'C++', 'C/C++ Header', 'Elixir', 'Scala',
    }

    IGNORE_DIRS = {
        '.git', '__pycache__', 'node_modules', '.venv', 'venv',
        'env', 'dist', 'build', '.idea', '.vscode', 'migrations',
        '.next', '.nuxt', 'coverage', '.pytest_cache', '.mypy_cache',
        'target', 'vendor', 'bower_components',
    }

    def __init__(self, project_path: str):
        if not project_path:
            raise ValueError("project_path no puede ser None o vacío")

        p = Path(project_path)
        try:
            p = p.resolve()
        except Exception:
            p = Path(project_path)

        if p.exists() and p.is_file():
            suffix = p.suffix.lower()
            if suffix in {'.zip', '.tar', '.gz', '.tgz', '.tar.gz'}:
                try:
                    import zipfile, tarfile
                    dest = p.parent / 'src'
                    dest.mkdir(parents=True, exist_ok=True)
                    if suffix == '.zip':
                        with zipfile.ZipFile(p, 'r') as z:
                            z.extractall(dest)
                    else:
                        with tarfile.open(p, 'r:*') as t:
                            t.extractall(dest)
                    p = dest.resolve()
                except Exception:
                    p = p.parent
            else:
                p = p.parent

        if not p.exists():
            raise ValueError(f"La ruta del proyecto no existe: {project_path}")

        if not p.is_dir():
            raise ValueError(f"La ruta no es un directorio: {project_path}")

        self.project_path = p
        self.results = {
            "total_files": 0, "primary_language": "unknown",
            "languages": {}, "structure": [], "functions": [],
            "classes": [], "endpoints": [], "imports": [],
            "quality_score": 0, "complexity": {}, "issues": []
        }

    def analyze(self) -> dict:
        """
        Ejecuta el pipeline completo de análisis.

        1. Recorre el proyecto y detecta archivos/lenguajes.
        2. Calcula el lenguaje principal.
        3. Extrae funciones, clases y endpoints según el lenguaje.
        4. Calcula la puntuación de calidad del proyecto.
        """
        if not self.project_path.exists():
            self.results["error"] = "Project path does not exist"
            return self.results

        # Paso 1: construir la estructura y contar lenguajes.
        self._scan_structure()

        # Paso 2: identificar el lenguaje dominante del proyecto.
        self._detect_primary_language()

        # Paso 3: analizar archivos relevantes para extraer funciones y endpoints.
        self._analyze_code_files()

        # Paso 4: calcular métricas agregadas de calidad.
        self._calculate_quality_score()
        return self.results

    def _scan_structure(self):
        """
        Recorre todos los archivos del proyecto y guarda:
        - ruta relativa
        - nombre
        - extensión
        - lenguaje inferido
        - tamaño

        Solo guarda un máximo de 300 archivos para no cargar demasiado la respuesta.
        """
        structure = []
        lang_count = defaultdict(int)
        total = 0
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            rel_root = Path(root).relative_to(self.project_path)
            for fname in files:
                full_path = Path(root) / fname
                ext = Path(fname).suffix.lower()
                lang = self.LANGUAGE_EXTENSIONS.get(ext)
                if not lang and full_path.exists():
                    lang = self._guess_language_by_shebang(full_path)
                if lang:
                    lang_count[lang] += 1
                    total += 1
                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0
                structure.append({
                    "path": str(rel_root / fname), "name": fname, "type": "file",
                    "language": lang or "other", "size": size, "extension": ext,
                })
        self.results["structure"] = structure[:300]
        self.results["total_files"] = total
        self.results["languages"] = dict(lang_count)

    def _detect_primary_language(self):
        """
        Elige el lenguaje principal del proyecto.

        Se excluyen archivos de configuración (JSON, YAML, HTML, CSS, etc.)
        para que el lenguaje dominante refleje el código real del proyecto.
        """
        config_langs = {'JSON', 'YAML', 'TOML', 'INI', 'XML', 'HTML', 'CSS',
                        'SCSS', 'Sass', 'LESS', 'SQL', 'C/C++ Header'}
        langs = {k: v for k, v in self.results["languages"].items() if k not in config_langs}
        if langs:
            self.results["primary_language"] = max(langs, key=langs.get)
        elif self.results["languages"]:
            self.results["primary_language"] = max(self.results["languages"], key=self.results["languages"].get)

    def _guess_language_by_shebang(self, filepath: Path):
        try:
            first_line = filepath.read_text(encoding='utf-8', errors='ignore').splitlines()[0].strip()
        except Exception:
            return None
        if first_line.startswith('#!'):
            if 'python' in first_line:
                return 'Python'
            if 'node' in first_line or 'nodejs' in first_line:
                return 'JavaScript'
            if 'bash' in first_line or 'sh' in first_line:
                return 'Shell'
            if 'ruby' in first_line:
                return 'Ruby'
            if 'perl' in first_line:
                return 'Perl'
            if 'php' in first_line:
                return 'PHP'
            if 'lua' in first_line:
                return 'Lua'
            if 'dart' in first_line:
                return 'Dart'
            if 'pwsh' in first_line or 'powershell' in first_line:
                return 'PowerShell'
        return None

    def _analyze_code_files(self):
        """
        Selecciona el analizador correcto para cada archivo detectado.

        El diccionario `dispatch` mapea el lenguaje a su función específica,
        evitando tener que hacer ifs repetitivos para cada archivo.
        """
        dispatch = {
            'Python': self._analyze_python_file,
            'JavaScript': self._analyze_js_ts_file,
            'TypeScript': self._analyze_js_ts_file,
            'React (JSX)': self._analyze_js_ts_file,
            'React (TSX)': self._analyze_js_ts_file,
            'Java': self._analyze_java_file,
            'PHP': self._analyze_php_file,
            'Ruby': self._analyze_ruby_file,
            'Go': self._analyze_go_file,
            'C#': self._analyze_csharp_file,
            'Kotlin': self._analyze_kotlin_file,
            'Rust': self._analyze_rust_file,
            'Swift': self._analyze_swift_file,
            'C': self._analyze_c_cpp_file,
            'C++': self._analyze_c_cpp_file,
            'C/C++ Header': self._analyze_c_cpp_file,
            'Scala': self._analyze_scala_file,
            'Elixir': self._analyze_elixir_file,
        }
        for item in self.results["structure"]:
            lang = item["language"]
            fn = dispatch.get(lang)
            if fn:
                fn(self.project_path / item["path"])

    # ── Python ────────────────────────────────────────────────────────
    def _analyze_python_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(source)
            rel = str(filepath.relative_to(self.project_path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.results["functions"].append({
                        "name": node.name, "file": rel, "line": node.lineno,
                        "params": [a.arg for a in node.args.args],
                        "docstring": ast.get_docstring(node) or "",
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "complexity": self._estimate_complexity(node),
                    })
                elif isinstance(node, ast.ClassDef):
                    bases = []
                    for b in node.bases:
                        try:
                            bases.append(ast.unparse(b) if hasattr(ast, 'unparse') else str(b))
                        except Exception:
                            pass
                    self.results["classes"].append({
                        "name": node.name, "file": rel, "line": node.lineno,
                        "methods": [n.name for n in ast.walk(node)
                                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                        "bases": bases, "docstring": ast.get_docstring(node) or "",
                    })
            self._detect_python_endpoints(source, rel)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    def _detect_python_endpoints(self, source, filepath):
        """
        Detecta endpoints en archivos Python usando patrones habituales de frameworks.

        Soporta Flask/FastAPI, rutas con `methods=` y decoradores de Django.
        """
        patterns = [
            (r'@(?:\w+)\.(get|post|put|delete|patch|options|head)\(\s*["\']([^"\']+)["\']', 'Flask/FastAPI'),
            (r'@(?:\w+)\.route\(\s*["\']([^"\']+)["\'].*?methods\s*=\s*\[([^\]]+)\]', 'Flask'),
            (r'path\(\s*["\']([^"\']*)["\']', 'Django'),
        ]
        for pattern, framework in patterns:
            for m in re.finditer(pattern, source, re.IGNORECASE | re.DOTALL):
                g = m.groups()
                if len(g) == 2:
                    a, b = g
                    if re.search(r'["\']', str(b)):
                        for method in re.findall(r'["\'](\w+)["\']', b):
                            self.results["endpoints"].append({"method": method.upper(), "path": a, "file": filepath, "framework": framework})
                    else:
                        self.results["endpoints"].append({"method": b.upper(), "path": a, "file": filepath, "framework": framework})
                elif len(g) == 1:
                    self.results["endpoints"].append({"method": "GET", "path": g[0], "file": filepath, "framework": framework})

    # ── JS / TS ───────────────────────────────────────────────────────
    def _analyze_js_ts_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            # Routes
            for m in re.finditer(r'(?:app|router)\.(get|post|put|delete|patch|options)\(\s*["`\']([^"`\']+)["`\']', source, re.I):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "Express.js"})
            for m in re.finditer(r'@(Get|Post|Put|Delete|Patch)\(\s*["`\']?([^"`\'\)]*)["`\']?\)', source):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2) or '/', "file": rel, "framework": "NestJS"})
            # Functions
            for pattern in [
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)',
            ]:
                for m in re.finditer(pattern, source):
                    name, params_str = m.groups()
                    if name and len(name) > 1:
                        params = [p.strip().split(':')[0].strip() for p in params_str.split(',') if p.strip()]
                        self.results["functions"].append({"name": name, "file": rel, "params": params, "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            # Classes
            for m in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Java ──────────────────────────────────────────────────────────
    def _analyze_java_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            method_map = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE', 'PatchMapping': 'PATCH', 'RequestMapping': 'GET'}
            for m in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\(?["\']?([^"\')\n]*)["\']?\)?', source):
                self.results["endpoints"].append({"method": method_map.get(m.group(1), 'GET'), "path": m.group(2).strip() or '/', "file": rel, "framework": "Spring"})
            for m in re.finditer(r'(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                if name not in ('if', 'for', 'while', 'switch', 'return', 'class'):
                    self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:public\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── PHP ───────────────────────────────────────────────────────────
    def _analyze_php_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'Route::(get|post|put|delete|patch|any)\s*\(\s*["\']([^"\']+)["\']', source, re.I):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "Laravel"})
            for m in re.finditer(r'(?:public\s+|private\s+|protected\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().lstrip('$') for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Ruby ──────────────────────────────────────────────────────────
    def _analyze_ruby_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(get|post|put|delete|patch)\s+["\']([^"\']+)["\']', source, re.I):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "Rails/Sinatra"})
            for m in re.finditer(r'def\s+(\w+)(?:\(([^)]*)\))?', source):
                name, ps = m.group(1), m.group(2) or ''
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*<\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Go ────────────────────────────────────────────────────────────
    def _analyze_go_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:r|router|e|app|mux)\.(GET|POST|PUT|DELETE|PATCH|HandleFunc|Handle)\(\s*["`]([^"`]+)["`]', source, re.I):
                method = m.group(1).upper().replace('HANDLEFUNC', 'GET').replace('HANDLE', 'GET')
                self.results["endpoints"].append({"method": method, "path": m.group(2), "file": rel, "framework": "Go HTTP (Gin/Echo/Fiber)"})
            for m in re.finditer(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'type\s+(\w+)\s+struct\s*\{', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── C# ────────────────────────────────────────────────────────────
    def _analyze_csharp_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            mm = {'HttpGet': 'GET', 'HttpPost': 'POST', 'HttpPut': 'PUT', 'HttpDelete': 'DELETE', 'HttpPatch': 'PATCH', 'Route': 'GET'}
            for m in re.finditer(r'\[(HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch|Route)(?:\(["\']([^"\']*)["\'])?\]', source):
                self.results["endpoints"].append({"method": mm.get(m.group(1), 'GET'), "path": m.group(2) or '/', "file": rel, "framework": "ASP.NET Core"})
            for m in re.finditer(r'(?:public|private|protected|internal)\s+(?:async\s+)?(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            for m in re.finditer(r'(?:public\s+)?class\s+(\w+)(?:\s*:\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Kotlin ────────────────────────────────────────────────────────
    def _analyze_kotlin_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            mm = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE', 'PatchMapping': 'PATCH'}
            for m in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\(?["\']?([^"\')\n]*)["\']?\)?', source):
                self.results["endpoints"].append({"method": mm.get(m.group(1), 'GET'), "path": m.group(2).strip() or '/', "file": rel, "framework": "Spring/Ktor"})
            for m in re.finditer(r'fun\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:data\s+)?class\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Rust ──────────────────────────────────────────────────────────
    def _analyze_rust_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'#\[(?:get|post|put|delete|patch)\("[^"]*"\)\]', source):
                method = re.search(r'#\[(\w+)', m.group(0))
                path_ = re.search(r'"([^"]+)"', m.group(0))
                if method and path_:
                    self.results["endpoints"].append({"method": method.group(1).upper(), "path": path_.group(1), "file": rel, "framework": "Actix/Axum"})
            for m in re.finditer(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*)?\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            for m in re.finditer(r'(?:pub\s+)?struct\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Swift ─────────────────────────────────────────────────────────
    def _analyze_swift_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:func)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*:\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── C / C++ ───────────────────────────────────────────────────────
    def _analyze_c_cpp_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:[\w*]+\s+)+(\w+)\s*\(([^)]*)\)\s*(?:const\s*)?\{', source):
                name, ps = m.groups()
                if name not in ('if', 'for', 'while', 'switch', 'return', 'do'):
                    self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1].lstrip('*') for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*:\s*(?:public|private|protected)?\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Scala ─────────────────────────────────────────────────────────
    def _analyze_scala_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'def\s+(\w+)\s*(?:\(([^)]*)\))?', source):
                name, ps = m.group(1), m.group(2) or ''
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:class|object|trait|case class)\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Elixir ────────────────────────────────────────────────────────
    def _analyze_elixir_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(get|post|put|delete|patch)\s+"([^"]+)"', source, re.I):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "Phoenix"})
            for m in re.finditer(r'def\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'defmodule\s+([\w.]+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Helpers ───────────────────────────────────────────────────────
    def _estimate_complexity(self, node) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                   ast.With, ast.Assert, ast.comprehension,
                                   ast.BoolOp, ast.Try)):
                complexity += 1
        return complexity

    def _calculate_quality_score(self):
        """
        Calcula una puntuación global del proyecto.

        Se penaliza por falta de documentación, complejidad alta y errores
        detectados durante el análisis. Se premia la presencia de tests.
        """
        score = 100
        funcs = self.results["functions"]
        if funcs:
            documented = sum(1 for f in funcs if f.get("docstring"))
            score -= (1 - documented / len(funcs)) * 30
        high_cx = sum(1 for f in funcs if f.get("complexity", 1) > 10)
        score -= min(high_cx * 5, 20)
        issues = len(self.results.get("issues", []))
        score -= min(issues * 2, 20)
        test_fns = sum(1 for f in funcs if 'test' in f['name'].lower())
        if test_fns:
            score = min(100, score + min(test_fns, 10))
        self.results["quality_score"] = max(0, int(score))
        self.results["complexity"] = {
            "avg": round(sum(f.get("complexity", 1) for f in funcs) / max(len(funcs), 1), 2),
            "max": max((f.get("complexity", 1) for f in funcs), default=0),
            "high_complexity_funcs": high_cx,
        }