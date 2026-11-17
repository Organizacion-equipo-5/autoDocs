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
    points = []
    for snapshot in snapshots:
        source = snapshot.get("source") or {}
        points.append({
            "id": str(snapshot["_id"]),
            "created_at": snapshot.get("created_at"),
            "quality_score": snapshot.get("quality_score", 0),
            "primary_language": snapshot.get("primary_language", "unknown"),
            "totals": snapshot.get("totals", {}),
            "source": source,
            "label": _source_label(source),
        })
    return points


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


def _function_changes(old, new):
    changes = []
    old_complexity = _number(old.get("complexity", 1))
    new_complexity = _number(new.get("complexity", 1))
    if old_complexity != new_complexity:
        changes.append(f"Complejidad {old_complexity} → {new_complexity}")
    if old.get("params") != new.get("params"):
        changes.append("Parámetros modificados")
    if old.get("is_async") != new.get("is_async"):
        changes.append("Cambió a asíncrona" if new.get("is_async") else "Cambió a síncrona")
    if old.get("docstring") != new.get("docstring"):
        changes.append("Documentación modificada")
    if old.get("code_snippet") != new.get("code_snippet"):
        changes.append("Código modificado")
    return changes


def _class_changes(old, new):
    changes = []
    if old.get("bases") != new.get("bases"):
        changes.append("Clases base modificadas")
    if old.get("methods") != new.get("methods"):
        changes.append("Métodos modificados")
    if old.get("docstring") != new.get("docstring"):
        changes.append("Documentación modificada")
    if old.get("code_snippet") != new.get("code_snippet"):
        changes.append("Código modificado")
    return changes


def _source_label(source):
    label = source.get("label")
    if label:
        return label
    branch = source.get("branch")
    sha = source.get("sha")
    short_sha = sha[:7] if isinstance(sha, str) and sha else None
    if branch:
        return branch + ("@" + short_sha if short_sha else "")
    return short_sha or source.get("event") or "manual"


def _snapshot_info(snapshot):
    source = snapshot.get("source") or {}
    return {
        "id": str(snapshot.get("_id", "")),
        "created_at": snapshot.get("created_at"),
        "quality_score": snapshot.get("quality_score", 0),
        "primary_language": snapshot.get("primary_language", "unknown"),
        "source": source,
        "label": _source_label(source),
    }


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
        old_function = old_functions[key]
        new_function = new_functions[key]
        changes = _function_changes(old_function, new_function)
        if changes:
            before = _number(old_function.get("complexity", 1))
            after = _number(new_function.get("complexity", 1))
            changed.append({
                "name": new_function.get("name", ""),
                "file": new_function.get("file", ""),
                "old_complexity": before,
                "new_complexity": after,
                "complexity_delta": after - before,
                "changes": changes,
            })
    functions["changed"] = changed
    old_unmatched = functions["removed"]
    new_unmatched = functions["added"]
    old_name_counts = {}
    new_name_counts = {}
    for function in old_unmatched:
        name = function.get("name")
        old_name_counts[name] = old_name_counts.get(name, 0) + 1
    for function in new_unmatched:
        name = function.get("name")
        new_name_counts[name] = new_name_counts.get(name, 0) + 1
    moved = []
    moved_old_keys = set()
    moved_new_keys = set()
    new_by_name = {
        function.get("name"): function
        for function in new_unmatched
        if function.get("name") and new_name_counts.get(function.get("name")) == 1
    }
    for function in old_unmatched:
        name = function.get("name")
        if name and old_name_counts.get(name) == 1 and name in new_by_name:
            target = new_by_name[name]
            moved.append({
                "name": name,
                "from": function.get("file", ""),
                "to": target.get("file", ""),
            })
            moved_old_keys.add(_symbol_key(function, ("name", "file")))
            moved_new_keys.add(_symbol_key(target, ("name", "file")))
    functions["removed"] = [
        item for item in old_unmatched
        if _symbol_key(item, ("name", "file")) not in moved_old_keys
    ]
    functions["added"] = [
        item for item in new_unmatched
        if _symbol_key(item, ("name", "file")) not in moved_new_keys
    ]
    functions["moved"] = moved
    functions["counts"] = {
        "added": len(functions["added"]),
        "removed": len(functions["removed"]),
        "changed": len(changed),
        "moved": len(moved),
    }

    old_classes = {
        _symbol_key(item, ("name", "file")): item for item in old.get("classes") or []
    }
    new_classes = {
        _symbol_key(item, ("name", "file")): item for item in new.get("classes") or []
    }
    class_changes = []
    for key in sorted(old_classes.keys() & new_classes.keys()):
        changes = _class_changes(old_classes[key], new_classes[key])
        if changes:
            class_changes.append({
                "name": new_classes[key].get("name", ""),
                "file": new_classes[key].get("file", ""),
                "changes": changes,
            })
    classes["changed"] = class_changes
    classes["counts"]["changed"] = len(class_changes)

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

    summary = {
        "functions_added": functions["counts"]["added"],
        "functions_removed": functions["counts"]["removed"],
        "functions_changed": functions["counts"]["changed"],
        "functions_moved": functions["counts"]["moved"],
        "classes_added": classes["counts"]["added"],
        "classes_removed": classes["counts"]["removed"],
        "classes_changed": classes["counts"]["changed"],
        "endpoints_added": endpoints["counts"]["added"],
        "endpoints_removed": endpoints["counts"]["removed"],
    }
    has_changes = (
        score["delta"] != 0
        or any(metric["delta"] != 0 for metric in totals.values())
        or bool(endpoints["added"] or endpoints["removed"])
        or bool(functions["added"] or functions["removed"] or changed or moved)
        or bool(classes["added"] or classes["removed"] or class_changes)
        or bool(hotspots)
    )
    summary["has_changes"] = has_changes
    return {
        "from": _snapshot_info(old),
        "to": _snapshot_info(new),
        "score": score,
        "totals": totals,
        "endpoints": endpoints,
        "functions": functions,
        "classes": classes,
        "hotspots": hotspots,
        "summary": summary,
    }
