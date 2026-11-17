"""Persist and compare project-analysis snapshots."""

from datetime import datetime
from uuid import uuid4


_METRICS = (
    ("files", "Archivos", False),
    ("functions", "Funciones", False),
    ("classes", "Clases", False),
    ("endpoints", "Endpoints", False),
    ("documented_functions", "Funciones documentadas", False),
    ("avg_complexity", "Complejidad media", True),
    ("high_complexity_funcs", "Funciones de alta complejidad", True),
    ("dead_code", "Código muerto", True),
    ("duplicated_lines", "Líneas duplicadas", True),
    ("hot_files", "Archivos de alto riesgo", True),
)


def _totals(results):
    functions = results.get("functions") or []
    health = results.get("code_health") or {}
    summary = health.get("summary") or {}
    complexity = results.get("complexity") or {}
    return {
        "files": results.get("total_files", 0),
        "functions": len(functions),
        "classes": len(results.get("classes") or []),
        "endpoints": len(results.get("endpoints") or []),
        "documented_functions": sum(bool(fn.get("docstring")) for fn in functions),
        "avg_complexity": complexity.get("avg", 0),
        "high_complexity_funcs": complexity.get("high_complexity_funcs", 0),
        "dead_code": summary.get("dead_code", 0),
        "duplicated_lines": summary.get("duplicated_lines", 0),
        "hot_files": summary.get("hot_files", 0),
    }


def save_snapshot(db, project_id, results, source=None):
    """Store the comparable summary and symbols for one completed analysis."""
    health = results.get("code_health") or {}
    heatmap = health.get("heatmap") or {}
    snapshot = {
        "_id": uuid4().hex,
        "project_id": project_id,
        "created_at": datetime.utcnow().isoformat(),
        "source": source or {},
        "primary_language": results.get("primary_language", "unknown"),
        "quality_score": results.get("quality_score", 0),
        "totals": _totals(results),
        "endpoints": list(results.get("endpoints") or []),
        "functions": list(results.get("functions") or []),
        "classes": list(results.get("classes") or []),
        "hotspots": list(heatmap.get("files") or []),
    }
    db.analysis_snapshots.insert_one(snapshot)
    return snapshot


def list_snapshots(db, project_id):
    """Return a project's snapshots in chronological order."""
    return list(
        db.analysis_snapshots.find({"project_id": project_id}).sort("created_at", 1)
    )


def trend(snapshots):
    """Project snapshots into the fields needed for a history chart."""
    return [
        {
            "id": str(snapshot["_id"]),
            "created_at": snapshot.get("created_at"),
            "quality_score": snapshot.get("quality_score", 0),
            "primary_language": snapshot.get("primary_language", "unknown"),
            "totals": snapshot.get("totals", {}),
            "source": snapshot.get("source", {}),
        }
        for snapshot in snapshots
    ]


def _select_snapshot(snapshots, selector):
    if selector is None:
        return None
    for snapshot in snapshots:
        if str(snapshot.get("_id")) == selector:
            return snapshot
        if (snapshot.get("source") or {}).get("sha") == selector:
            return snapshot
    return None


def resolve_pair(db, project_id, from_id=None, to_id=None):
    """Resolve snapshot IDs (or commit SHAs), defaulting to oldest and newest."""
    snapshots = list_snapshots(db, project_id)
    if len(snapshots) < 2:
        raise LookupError("Se necesitan al menos dos análisis para compararlos.")

    old = _select_snapshot(snapshots, from_id) if from_id else snapshots[0]
    new = _select_snapshot(snapshots, to_id) if to_id else snapshots[-1]
    if old is None:
        raise LookupError("No se encontró el análisis indicado en 'from'.")
    if new is None:
        raise LookupError("No se encontró el análisis indicado en 'to'.")
    return old, new


def _symbol_key(symbol, fields):
    return tuple(symbol.get(field, "") for field in fields)


def _compare_symbols(old_items, new_items, fields):
    old_by_key = {_symbol_key(item, fields): item for item in old_items or []}
    new_by_key = {_symbol_key(item, fields): item for item in new_items or []}
    added_keys = new_by_key.keys() - old_by_key.keys()
    removed_keys = old_by_key.keys() - new_by_key.keys()
    added = [new_by_key[key] for key in sorted(added_keys)]
    removed = [old_by_key[key] for key in sorted(removed_keys)]
    return {
        "added": added,
        "removed": removed,
        "counts": {"added": len(added), "removed": len(removed)},
    }


def _number(value):
    return value if isinstance(value, (int, float)) else 0


def diff_snapshots(old, new):
    """Compare two snapshots using the response shape consumed by CI reports."""
    old_score = _number(old.get("quality_score", 0))
    new_score = _number(new.get("quality_score", 0))
    score = {"old": old_score, "new": new_score, "delta": new_score - old_score}

    old_totals = old.get("totals") or {}
    new_totals = new.get("totals") or {}
    totals = {}
    for key, label, lower_is_better in _METRICS:
        old_value = _number(old_totals.get(key, 0))
        new_value = _number(new_totals.get(key, 0))
        totals[key] = {
            "label": label,
            "old": old_value,
            "new": new_value,
            "delta": new_value - old_value,
            "lower_is_better": lower_is_better,
        }

    endpoints = _compare_symbols(old.get("endpoints"), new.get("endpoints"),
                                 ("method", "path", "file"))
    functions = _compare_symbols(old.get("functions"), new.get("functions"),
                                 ("name", "file"))
    classes = _compare_symbols(old.get("classes"), new.get("classes"),
                               ("name", "file"))
    old_functions = {
        _symbol_key(item, ("name", "file")): item for item in old.get("functions") or []
    }
    new_functions = {
        _symbol_key(item, ("name", "file")): item for item in new.get("functions") or []
    }
    changed = []
    for key in sorted(old_functions.keys() & new_functions.keys()):
        before = _number(old_functions[key].get("complexity", 1))
        after = _number(new_functions[key].get("complexity", 1))
        if before != after:
            changed.append({
                "name": new_functions[key].get("name", ""),
                "file": new_functions[key].get("file", ""),
                "old_complexity": before,
                "new_complexity": after,
                "complexity_delta": after - before,
            })
    functions["changed"] = changed

    old_hotspots = {
        item.get("file"): item.get("score")
        for item in old.get("hotspots") or [] if item.get("file")
    }
    new_hotspots = {
        item.get("file"): item.get("score")
        for item in new.get("hotspots") or [] if item.get("file")
    }
    hotspots = [
        {
            "file": filename,
            "old": old_hotspots.get(filename),
            "new": new_hotspots.get(filename),
        }
        for filename in sorted(old_hotspots.keys() | new_hotspots.keys())
        if old_hotspots.get(filename) != new_hotspots.get(filename)
    ]
    hotspots.sort(key=lambda item: (
        -(item["new"] if item["new"] is not None else -1), item["file"]
    ))

    has_changes = (
        score["delta"] != 0
        or any(metric["delta"] != 0 for metric in totals.values())
        or bool(endpoints["added"] or endpoints["removed"])
        or bool(functions["added"] or functions["removed"] or changed)
        or bool(classes["added"] or classes["removed"])
        or bool(hotspots)
    )
    return {
        "score": score,
        "totals": totals,
        "endpoints": endpoints,
        "functions": functions,
        "classes": classes,
        "hotspots": hotspots,
        "summary": {"has_changes": has_changes},
    }
