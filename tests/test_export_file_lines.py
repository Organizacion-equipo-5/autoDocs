from routes.export import _populate_file_line_counts


def test_populates_missing_line_counts_only_inside_project(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text("one\ntwo\n", encoding="utf-8")
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("must not be read", encoding="utf-8")
    results = {
        "structure": [
            {"path": "main.py"},
            {"path": "../outside.py"},
        ]
    }

    _populate_file_line_counts(results, {"file_path": str(project_dir)})

    assert results["structure"][0]["line_count"] == 2
    assert "line_count" not in results["structure"][1]
