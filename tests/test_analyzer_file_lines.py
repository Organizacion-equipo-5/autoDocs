from services.analyzer import ProjectAnalyzer


def test_scan_structure_counts_physical_lines_per_file(tmp_path):
    source = tmp_path / "main.py"
    source.write_text("first line\nsecond line\nthird line", encoding="utf-8")
    analyzer = ProjectAnalyzer(str(tmp_path))

    analyzer._scan_structure()

    file_entry = next(item for item in analyzer.results["structure"] if item["name"] == "main.py")
    assert file_entry["line_count"] == 3
