from types import SimpleNamespace

from services.analysis_history import diff_snapshots, list_snapshots, resolve_pair, save_snapshot, trend


class SnapshotCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(document)

    def find(self, query):
        matches = [
            document for document in self.documents
            if document["project_id"] == query["project_id"]
        ]
        return SnapshotCursor(matches)


class SnapshotCursor(list):
    def sort(self, key, direction):
        return SnapshotCursor(sorted(
            self, key=lambda document: document[key], reverse=direction < 0
        ))


def test_save_list_trend_and_resolve_pair():
    db = SimpleNamespace(analysis_snapshots=SnapshotCollection())
    old = save_snapshot(db, "project-1", {
        "quality_score": 70,
        "functions": [{"name": "run", "file": "app.py", "complexity": 2}],
    }, source={"sha": "base"})
    new = save_snapshot(db, "project-1", {
        "quality_score": 80,
        "functions": [{"name": "run", "file": "app.py", "complexity": 4}],
    }, source={"sha": "head"})

    snapshots = list_snapshots(db, "project-1")
    assert [item["_id"] for item in snapshots] == [old["_id"], new["_id"]]
    assert [item["quality_score"] for item in trend(snapshots)] == [70, 80]
    assert resolve_pair(db, "project-1", "base", "head") == (old, new)


def test_diff_snapshots_reports_symbol_and_complexity_changes():
    old = {
        "quality_score": 70,
        "totals": {"functions": 1},
        "functions": [{"name": "run", "file": "app.py", "complexity": 2}],
        "endpoints": [],
        "classes": [],
        "hotspots": [],
    }
    new = {
        "quality_score": 80,
        "totals": {"functions": 2},
        "functions": [
            {"name": "run", "file": "app.py", "complexity": 4},
            {"name": "start", "file": "app.py", "complexity": 1},
        ],
        "endpoints": [],
        "classes": [],
        "hotspots": [],
    }

    diff = diff_snapshots(old, new)

    assert diff["score"] == {"old": 70, "new": 80, "delta": 10}
    assert diff["functions"]["counts"] == {"added": 1, "removed": 0}
    assert diff["functions"]["changed"][0]["complexity_delta"] == 2
    assert diff["summary"]["has_changes"] is True
