"""
services/analysis_history.py

Historial de análisis por proyecto y comparación entre versiones.

Cada vez que se analiza un proyecto se guarda un "snapshot" compacto (sin código
fuente) en la colección ``analysis_history``. Con dos snapshots se puede calcular:

- qué funciones, clases y endpoints se agregaron, eliminaron, movieron o cambiaron
- cuánto cambiaron las métricas (score de calidad, complejidad, código muerto...)
- la tendencia del score a lo largo del tiempo

La parte de construcción y comparación (build_snapshot, diff_snapshots, trend) no
depende de Flask ni de MongoDB, por lo que también la usa la GitHub Action.
"""
import uuid
from datetime import datetime

SNAPSHOT_VERSION = 1
MAX_ITEMS = 5000                    # tope de elementos por lista dentro de un snapshot
MAX_SNAPSHOTS_PER_PROJECT = 50      # se borran los más antiguos al superarlo
MAX_DIFF_ITEMS = 200                # tope de elementos devueltos por sección del diff

TOTAL_LABELS = {
    "files": "Archivos",
    "functions": "Funciones",
    "classes": "Clases",
    "endpoints": "Endpoints",
    "issues": "Errores de análisis",
    "documented_functions": "Funciones documentadas",
    "avg_complexity": "Complejidad promedio",
    "high_complexity_funcs": "Funciones muy complejas (>10)",
    "dead_code": "Código muerto",
    "duplicate_groups": "Bloques duplicados",
    "duplicated_lines": "Líneas duplicadas",
    "hot_files": "Archivos en zona caliente",
}
# Métricas donde "subir" es malo (se usa para colorear/valorar el cambio)
LOWER_IS_BETTER = {
    "issues", "avg_complexity", "high_complexity_funcs", "dead_code",
    "duplicate_groups", "duplicated_lines", "hot_files",
}


# ── Construcción de snapshots ────────────────────────────────────────────────
def _keyed(items, key_fn):
    """Asigna una clave única a cada elemento (desambigua repetidos con #n)."""
    seen = {}
    out = []
    for item in items:
        base = key_fn(item)
        n = seen.get(base, 0)
        seen[base] = n + 1
        out.append((base if n == 0 else f"{base}#{n}", item))
    return out


def _clean_source(source):
    if not isinstance(source, dict):
        return {}
    allowed = ("event", "sha", "branch", "message", "repo", "actor", "pr")
    out = {}
    for k in allowed:
        v = source.get(k)
        if v is not None and v != "":
            out[k] = str(v)[:200]
    return out


def build_snapshot(results: dict, source: dict = None, created_at: str = None) -> dict:
    """Resume los resultados de ProjectAnalyzer en un snapshot comparable y compacto."""
    results = results or {}
    functions = []
    for key, fn in _keyed(results.get("functions", []) or [],
                          lambda f: f"{f.get('file', '')}::{f.get('name', '')}"):
        functions.append({
            "key": key, "name": fn.get("name", ""), "file": fn.get("file", ""),
            "line": fn.get("line") or 0, "params": list(fn.get("params", []) or []),
            "complexity": int(fn.get("complexity", 1) or 1),
            "documented": bool(fn.get("docstring")),
        })
    classes = []
    for key, cl in _keyed(results.get("classes", []) or [],
                          lambda c: f"{c.get('file', '')}::{c.get('name', '')}"):
        classes.append({
            "key": key, "name": cl.get("name", ""), "file": cl.get("file", ""),
            "methods": sorted(set(cl.get("methods", []) or [])),
            "bases": list(cl.get("bases", []) or []),
            "documented": bool(cl.get("docstring")),
        })
    endpoints = []
    for key, ep in _keyed(results.get("endpoints", []) or [],
                          lambda e: f"{str(e.get('method', '')).upper()} {e.get('path', '')}"):
        endpoints.append({
            "key": key, "method": str(ep.get("method", "")).upper(),
            "path": ep.get("path", ""), "file": ep.get("file", ""),
        })

    health = results.get("code_health") or {}
    health_summary = health.get("summary") or {}
    hotspots = [
        {"file": e["file"], "score": e["score"]}
        for e in (health.get("heatmap", {}).get("files", []) or [])[:10]
    ]
    cx = results.get("complexity") or {}

    totals = {
        "files": results.get("total_files", 0),
        "functions": len(functions),
        "classes": len(classes),
        "endpoints": len(endpoints),
        "issues": len(results.get("issues", []) or []),
        "documented_functions": sum(1 for f in functions if f["documented"]),
        "avg_complexity": cx.get("avg", 0),
        "high_complexity_funcs": cx.get("high_complexity_funcs", 0),
    }
    if health_summary:
        totals.update({
            "dead_code": health_summary.get("dead_code", 0),
            "duplicate_groups": health_summary.get("duplicate_groups", 0),
            "duplicated_lines": health_summary.get("duplicated_lines", 0),
            "hot_files": health_summary.get("hot_files", 0),
        })

    return {
        "version": SNAPSHOT_VERSION,
        "created_at": created_at or datetime.utcnow().isoformat(),
        "source": _clean_source(source),
        "primary_language": results.get("primary_language", "unknown"),
        "quality_score": results.get("quality_score", 0),
        "totals": totals,
        "hotspots": hotspots,
        "functions": functions[:MAX_ITEMS],
        "classes": classes[:MAX_ITEMS],
        "endpoints": endpoints[:MAX_ITEMS],
    }


# ── Comparación ──────────────────────────────────────────────────────────────
def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _metric(old, new):
    o, n = _num(old), _num(new)
    delta = round(n - o, 2) if o is not None and n is not None else None
    return {"old": old, "new": new, "delta": delta}


def _cap(items):
    return items[:MAX_DIFF_ITEMS]


def _params_text(params):
    return "(" + ", ".join(params) + ")"


def _diff_functions(old_list, new_list):
    old = {f["key"]: f for f in old_list}
    new = {f["key"]: f for f in new_list}
    added = [new[k] for k in new if k not in old]
    removed = [old[k] for k in old if k not in new]

    # Detectar funciones movidas de archivo (mismo nombre y parámetros)
    moved = []
    pool = {}
    for r in removed:
        pool.setdefault((r["name"], tuple(r["params"])), []).append(r)
    still_added = []
    for a in added:
        candidates = pool.get((a["name"], tuple(a["params"])))
        if candidates:
            r = candidates.pop(0)
            moved.append({"name": a["name"], "from": r["file"], "to": a["file"]})
        else:
            still_added.append(a)
    moved_from = {(m["name"], m["from"]) for m in moved}
    still_removed = [r for r in removed if (r["name"], r["file"]) not in moved_from]

    changed = []
    for k in new:
        if k not in old:
            continue
        o, n = old[k], new[k]
        changes = []
        if o["params"] != n["params"]:
            changes.append(f"parámetros: {_params_text(o['params'])} → {_params_text(n['params'])}")
        if o["complexity"] != n["complexity"]:
            changes.append(f"complejidad: {o['complexity']} → {n['complexity']}")
        if o["documented"] != n["documented"]:
            changes.append("docstring añadido" if n["documented"] else "docstring eliminado")
        if changes:
            changed.append({
                "name": n["name"], "file": n["file"], "changes": changes,
                "complexity_delta": n["complexity"] - o["complexity"],
            })

    def slim(f):
        return {"name": f["name"], "file": f["file"], "complexity": f["complexity"]}

    return {
        "added": _cap([slim(f) for f in still_added]),
        "removed": _cap([slim(f) for f in still_removed]),
        "moved": _cap(moved),
        "changed": _cap(changed),
        "counts": {"added": len(still_added), "removed": len(still_removed),
                   "moved": len(moved), "changed": len(changed)},
    }


def _diff_classes(old_list, new_list):
    old = {c["key"]: c for c in old_list}
    new = {c["key"]: c for c in new_list}
    added = [{"name": c["name"], "file": c["file"]} for k, c in new.items() if k not in old]
    removed = [{"name": c["name"], "file": c["file"]} for k, c in old.items() if k not in new]
    changed = []
    for k, n in new.items():
        o = old.get(k)
        if not o:
            continue
        changes = []
        added_m = sorted(set(n["methods"]) - set(o["methods"]))
        removed_m = sorted(set(o["methods"]) - set(n["methods"]))
        if added_m:
            changes.append("métodos añadidos: " + ", ".join(added_m[:8]))
        if removed_m:
            changes.append("métodos eliminados: " + ", ".join(removed_m[:8]))
        if o["bases"] != n["bases"]:
            changes.append(f"herencia: {', '.join(o['bases']) or '—'} → {', '.join(n['bases']) or '—'}")
        if changes:
            changed.append({"name": n["name"], "file": n["file"], "changes": changes})
    return {
        "added": _cap(added), "removed": _cap(removed), "changed": _cap(changed),
        "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
    }


def _diff_endpoints(old_list, new_list):
    old = {e["key"]: e for e in old_list}
    new = {e["key"]: e for e in new_list}
    added = [{"method": e["method"], "path": e["path"], "file": e["file"]}
             for k, e in new.items() if k not in old]
    removed = [{"method": e["method"], "path": e["path"], "file": e["file"]}
               for k, e in old.items() if k not in new]
    return {
        "added": _cap(added), "removed": _cap(removed),
        "counts": {"added": len(added), "removed": len(removed)},
    }


def diff_snapshots(old: dict, new: dict) -> dict:
    """Compara dos snapshots (old → new) y devuelve las diferencias."""
    old_totals, new_totals = old.get("totals", {}), new.get("totals", {})
    totals = {}
    for key in TOTAL_LABELS:
        if key in old_totals or key in new_totals:
            m = _metric(old_totals.get(key), new_totals.get(key))
            m["label"] = TOTAL_LABELS[key]
            m["lower_is_better"] = key in LOWER_IS_BETTER
            totals[key] = m

    functions = _diff_functions(old.get("functions", []), new.get("functions", []))
    classes = _diff_classes(old.get("classes", []), new.get("classes", []))
    endpoints = _diff_endpoints(old.get("endpoints", []), new.get("endpoints", []))

    old_heat = {h["file"]: h["score"] for h in old.get("hotspots", [])}
    heat_changes = []
    for h in new.get("hotspots", []):
        before = old_heat.get(h["file"])
        if before is None or before != h["score"]:
            heat_changes.append({"file": h["file"], "old": before, "new": h["score"]})

    score = _metric(old.get("quality_score"), new.get("quality_score"))
    summary = {
        "score_delta": score["delta"],
        "functions_added": functions["counts"]["added"],
        "functions_removed": functions["counts"]["removed"],
        "functions_changed": functions["counts"]["changed"],
        "classes_added": classes["counts"]["added"],
        "classes_removed": classes["counts"]["removed"],
        "endpoints_added": endpoints["counts"]["added"],
        "endpoints_removed": endpoints["counts"]["removed"],
    }
    summary["has_changes"] = any(
        v for k, v in summary.items() if k != "score_delta"
    ) or bool(score["delta"])

    return {
        "from": {"created_at": old.get("created_at"), "source": old.get("source", {})},
        "to": {"created_at": new.get("created_at"), "source": new.get("source", {})},
        "score": score,
        "totals": totals,
        "functions": functions,
        "classes": classes,
        "endpoints": endpoints,
        "hotspots": _cap(heat_changes),
        "summary": summary,
    }


def trend(snapshots: list) -> list:
    """Serie temporal (más antiguo primero) para graficar la evolución del score."""
    points = []
    for s in sorted(snapshots, key=lambda x: (x.get("created_at", ""), str(x.get("_id", "")))):
        t = s.get("totals", {})
        points.append({
            "id": s.get("_id"),
            "created_at": s.get("created_at"),
            "label": (s.get("source") or {}).get("sha", "")[:7] or None,
            "source": s.get("source", {}),
            "quality_score": s.get("quality_score", 0),
            "functions": t.get("functions", 0),
            "classes": t.get("classes", 0),
            "endpoints": t.get("endpoints", 0),
            "dead_code": t.get("dead_code"),
            "duplicated_lines": t.get("duplicated_lines"),
            "avg_complexity": t.get("avg_complexity", 0),
        })
    return points


# ── Persistencia (MongoDB) ───────────────────────────────────────────────────
def save_snapshot(db, project_id: str, results: dict, source: dict = None) -> str:
    """Guarda un snapshot del análisis y poda los más antiguos. Devuelve su id."""
    doc = build_snapshot(results, source=source)
    doc["_id"] = str(uuid.uuid4())
    doc["project_id"] = project_id
    db.analysis_history.insert_one(doc)

    total = db.analysis_history.count_documents({"project_id": project_id})
    extra = total - MAX_SNAPSHOTS_PER_PROJECT
    if extra > 0:
        oldest = list(
            db.analysis_history.find({"project_id": project_id}, {"_id": 1})
            .sort("created_at", 1).limit(extra)
        )
        if oldest:
            db.analysis_history.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})
    return doc["_id"]


def list_snapshots(db, project_id: str, limit: int = MAX_SNAPSHOTS_PER_PROJECT) -> list:
    """Snapshots ligeros (sin listas de funciones/clases/endpoints), más antiguo primero."""
    cursor = (
        db.analysis_history.find(
            {"project_id": project_id},
            {"functions": 0, "classes": 0, "endpoints": 0},
        ).sort("created_at", -1).limit(limit)
    )
    return list(reversed(list(cursor)))


def get_snapshot(db, project_id: str, snapshot_id: str):
    return db.analysis_history.find_one({"_id": snapshot_id, "project_id": project_id})


def resolve_pair(db, project_id: str, from_id: str = None, to_id: str = None):
    """
    Devuelve (old, new). Por defecto compara el análisis más reciente contra el anterior.

    Raises:
        LookupError: si no existen snapshots suficientes o un id no pertenece al proyecto.
    """
    ordered = list(
        db.analysis_history.find({"project_id": project_id}, {"_id": 1, "created_at": 1})
        .sort("created_at", 1)
    )
    ids = [d["_id"] for d in ordered]
    if len(ids) < 2 and not (from_id and to_id):
        raise LookupError("Se necesitan al menos dos análisis del proyecto para comparar.")

    new_id = to_id or ids[-1]
    if from_id:
        old_id = from_id
    else:
        if new_id not in ids:
            raise LookupError("El análisis indicado no existe en este proyecto.")
        pos = ids.index(new_id)
        if pos == 0:
            raise LookupError("No hay un análisis anterior al seleccionado.")
        old_id = ids[pos - 1]

    old = get_snapshot(db, project_id, old_id)
    new = get_snapshot(db, project_id, new_id)
    if not old or not new:
        raise LookupError("Alguno de los análisis indicados no existe en este proyecto.")
    return old, new
