"""
tests/test_analysis_history.py

Pruebas de services/analysis_history.py: snapshots, comparación entre versiones,
tendencia y persistencia (mongomock).
Ejecutar con: python -m pytest tests/test_analysis_history.py -v
"""
import mongomock
import pytest

from services import analysis_history as ah


def fn(name, file="app.py", params=None, complexity=1, doc=""):
    return {"name": name, "file": file, "line": 1, "params": params or [],
            "complexity": complexity, "docstring": doc}


def results(functions=None, classes=None, endpoints=None, score=80, **extra):
    base = {"total_files": 3, "primary_language": "Python", "quality_score": score,
            "functions": functions or [], "classes": classes or [], "endpoints": endpoints or [],
            "issues": [], "complexity": {"avg": 2.0, "max": 5, "high_complexity_funcs": 0}}
    base.update(extra)
    return base


@pytest.fixture
def db():
    return mongomock.MongoClient().db


class TestBuildSnapshot:
    def test_totals_and_compact_items(self):
        snap = ah.build_snapshot(results(
            functions=[fn("a", doc="docs"), fn("b")],
            classes=[{"name": "C", "file": "c.py", "methods": ["m2", "m1"], "bases": ["Base"], "docstring": ""}],
            endpoints=[{"method": "get", "path": "/x", "file": "r.py"}]))
        assert snap["totals"]["functions"] == 2
        assert snap["totals"]["documented_functions"] == 1
        assert snap["totals"]["endpoints"] == 1
        assert snap["classes"][0]["methods"] == ["m1", "m2"]
        assert snap["endpoints"][0]["method"] == "GET"
        assert "code_snippet" not in snap["functions"][0]

    def test_repeated_names_get_unique_keys(self):
        snap = ah.build_snapshot(results(functions=[fn("dup"), fn("dup"), fn("dup")]))
        assert [f["key"] for f in snap["functions"]] == ["app.py::dup", "app.py::dup#1", "app.py::dup#2"]

    def test_code_health_totals_are_included_when_present(self):
        snap = ah.build_snapshot(results(code_health={
            "summary": {"dead_code": 2, "duplicate_groups": 1, "duplicated_lines": 9, "hot_files": 3},
            "heatmap": {"files": [{"file": "a.py", "score": 70}]}}))
        assert snap["totals"]["dead_code"] == 2 and snap["hotspots"] == [{"file": "a.py", "score": 70}]

    def test_source_is_whitelisted_and_trimmed(self):
        snap = ah.build_snapshot(results(), source={"sha": "x" * 500, "evil": "no", "event": "push"})
        assert set(snap["source"]) == {"sha", "event"} and len(snap["source"]["sha"]) == 200


class TestDiff:
    def test_detects_added_removed_changed_and_moved(self):
        old = ah.build_snapshot(results(score=70, functions=[
            fn("keep"), fn("gone"), fn("grow", params=["a"], complexity=3),
            fn("travel", file="old.py", params=["x"]), fn("doc_me")],
            endpoints=[{"method": "GET", "path": "/old", "file": "r.py"}]))
        new = ah.build_snapshot(results(score=75, functions=[
            fn("keep"), fn("fresh", complexity=12), fn("grow", params=["a", "b"], complexity=6),
            fn("travel", file="new.py", params=["x"]), fn("doc_me", doc="ahora sí")],
            endpoints=[{"method": "POST", "path": "/new", "file": "r.py"}]))
        diff = ah.diff_snapshots(old, new)

        assert diff["score"] == {"old": 70, "new": 75, "delta": 5}
        fns = diff["functions"]
        assert [f["name"] for f in fns["added"]] == ["fresh"]
        assert [f["name"] for f in fns["removed"]] == ["gone"]
        assert fns["moved"] == [{"name": "travel", "from": "old.py", "to": "new.py"}]
        changed = {c["name"]: c for c in fns["changed"]}
        assert set(changed) == {"grow", "doc_me"}
        assert any("parámetros" in x for x in changed["grow"]["changes"])
        assert changed["grow"]["complexity_delta"] == 3
        assert "docstring añadido" in changed["doc_me"]["changes"]
        assert [e["path"] for e in diff["endpoints"]["added"]] == ["/new"]
        assert [e["path"] for e in diff["endpoints"]["removed"]] == ["/old"]
        assert diff["summary"]["has_changes"] is True

    def test_class_changes(self):
        old = ah.build_snapshot(results(classes=[
            {"name": "A", "file": "a.py", "methods": ["x"], "bases": [], "docstring": ""},
            {"name": "Old", "file": "o.py", "methods": [], "bases": [], "docstring": ""}]))
        new = ah.build_snapshot(results(classes=[
            {"name": "A", "file": "a.py", "methods": ["x", "y"], "bases": ["Base"], "docstring": ""},
            {"name": "New", "file": "n.py", "methods": [], "bases": [], "docstring": ""}]))
        classes = ah.diff_snapshots(old, new)["classes"]
        assert [c["name"] for c in classes["added"]] == ["New"]
        assert [c["name"] for c in classes["removed"]] == ["Old"]
        assert "métodos añadidos: y" in classes["changed"][0]["changes"]

    def test_identical_snapshots_have_no_changes(self):
        snap = ah.build_snapshot(results(functions=[fn("a")]))
        diff = ah.diff_snapshots(snap, snap)
        assert diff["summary"]["has_changes"] is False and diff["score"]["delta"] == 0

    def test_totals_flag_which_direction_is_good(self):
        old = ah.build_snapshot(results(code_health={"summary": {"dead_code": 5}}))
        new = ah.build_snapshot(results(code_health={"summary": {"dead_code": 2}}))
        dead = ah.diff_snapshots(old, new)["totals"]["dead_code"]
        assert dead["delta"] == -3 and dead["lower_is_better"] is True

    def test_lists_are_capped(self):
        many = [fn(f"f{i}") for i in range(ah.MAX_DIFF_ITEMS + 50)]
        diff = ah.diff_snapshots(ah.build_snapshot(results()), ah.build_snapshot(results(functions=many)))
        assert len(diff["functions"]["added"]) == ah.MAX_DIFF_ITEMS
        assert diff["functions"]["counts"]["added"] == ah.MAX_DIFF_ITEMS + 50


class TestPersistence:
    def seed(self, db, n, project="p1"):
        ids = []
        for i in range(n):
            sid = ah.save_snapshot(db, project, results(score=60 + i, functions=[fn(f"f{j}") for j in range(i)]),
                                   source={"sha": f"abcdef{i}", "event": "push"})
            db.analysis_history.update_one({"_id": sid}, {"$set": {"created_at": f"2026-01-0{i + 1}T00:00:00"}})
            ids.append(sid)
        return ids

    def test_list_is_chronological_and_lightweight(self, db):
        ids = self.seed(db, 3)
        snaps = ah.list_snapshots(db, "p1")
        assert [s["_id"] for s in snaps] == ids
        assert "functions" not in snaps[0]
        assert [p["quality_score"] for p in ah.trend(snaps)] == [60, 61, 62]
        assert ah.trend(snaps)[0]["label"] == "abcdef0"

    def test_default_pair_is_latest_vs_previous(self, db):
        ids = self.seed(db, 3)
        old, new = ah.resolve_pair(db, "p1")
        assert (old["_id"], new["_id"]) == (ids[1], ids[2])
        old, new = ah.resolve_pair(db, "p1", from_id=ids[0], to_id=ids[2])
        assert (old["_id"], new["_id"]) == (ids[0], ids[2])

    def test_needs_two_snapshots_and_rejects_foreign_ids(self, db):
        ids = self.seed(db, 1)
        with pytest.raises(LookupError):
            ah.resolve_pair(db, "p1")
        other = self.seed(db, 2, project="p2")
        with pytest.raises(LookupError):
            ah.resolve_pair(db, "p1", from_id=ids[0], to_id=other[1])

    def test_old_snapshots_are_pruned(self, db, monkeypatch):
        monkeypatch.setattr(ah, "MAX_SNAPSHOTS_PER_PROJECT", 3)
        ids = self.seed(db, 3)
        newest = ah.save_snapshot(db, "p1", results())
        remaining = {s["_id"] for s in ah.list_snapshots(db, "p1")}
        assert len(remaining) == 3 and ids[0] not in remaining and newest in remaining
