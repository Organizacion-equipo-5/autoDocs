"""
tests/test_code_health.py

Pruebas de services/code_health.py: código muerto, duplicado y mapa de calor.
Ejecutar con: python -m pytest tests/test_code_health.py -v
"""
import pytest

from services.analyzer import ProjectAnalyzer
from services.code_health import analyze_code_health


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def health_of(root):
    results = ProjectAnalyzer(str(root)).analyze()
    return analyze_code_health(root, results), results


# Bloque de 8 líneas distintas y suficientemente largas para contar como duplicado
BLOCK = "\n".join(
    f"    value_{i} = compute_something(first_argument_{i}, second_argument_{i}, third_argument_{i})"
    for i in range(8)
)


class TestDeadCode:
    def test_python_orphan_function_is_reported(self, tmp_path):
        write(tmp_path, "app.py", (
            "def used_function():\n    return 1\n\n"
            "def orphan_function():\n    return 2\n\n"
            "def run_all():\n    return used_function()\n\n"
            "if __name__ == '__main__':\n    run_all()\n"
        ))
        health, _ = health_of(tmp_path)
        names = [d["name"] for d in health["dead_code"]["items"]]
        assert names == ["orphan_function"]
        item = health["dead_code"]["items"][0]
        assert item["file"] == "app.py" and item["line"] == 4 and item["confidence"] == "alta"

    def test_decorated_dunder_and_inherited_methods_are_not_reported(self, tmp_path):
        write(tmp_path, "views.py", (
            "from flask import Flask\napp = Flask(__name__)\n\n"
            "@app.route('/home')\ndef home_view():\n    return 'ok'\n\n"
            "class Base:\n    pass\n\n"
            "class Child(Base):\n"
            "    def __init__(self):\n        self.x = 1\n\n"
            "    def framework_hook(self):\n        return 3\n"
        ))
        health, _ = health_of(tmp_path)
        assert health["dead_code"]["count"] == 0

    def test_test_files_are_ignored(self, tmp_path):
        write(tmp_path, "tests/test_something.py", "def helper_never_called():\n    return 1\n")
        health, _ = health_of(tmp_path)
        assert health["dead_code"]["count"] == 0

    def test_name_used_in_a_template_counts_as_a_reference(self, tmp_path):
        write(tmp_path, "handlers.py", "def refresh_dashboard():\n    return 1\n")
        write(tmp_path, "page.html", "<button onclick=\"refresh_dashboard()\">go</button>\n")
        health, _ = health_of(tmp_path)
        assert health["dead_code"]["count"] == 0

    def test_javascript_orphan_has_medium_confidence(self, tmp_path):
        write(tmp_path, "lib.js", (
            "function usedFn() { return 1; }\n"
            "function unusedFn() { return 2; }\n"
            "usedFn();\n"
        ))
        health, _ = health_of(tmp_path)
        items = health["dead_code"]["items"]
        assert [i["name"] for i in items] == ["unusedFn"]
        assert items[0]["confidence"] == "media"

    def test_java_is_not_analyzed_for_dead_code(self, tmp_path):
        write(tmp_path, "Service.java", (
            "public class Service {\n    public void neverCalledMethod() {\n    }\n}\n"
        ))
        health, _ = health_of(tmp_path)
        assert health["dead_code"]["count"] == 0


class TestDuplicates:
    def test_identical_block_in_two_files_is_grouped_once(self, tmp_path):
        write(tmp_path, "a.py", f"def alpha():\n{BLOCK}\n    return value_0\n")
        write(tmp_path, "b.py", f"def beta():\n    other_line = 1\n{BLOCK}\n    return value_7\n")
        health, _ = health_of(tmp_path)
        groups = health["duplicates"]["items"]
        assert len(groups) == 1
        files = {o["file"] for o in groups[0]["occurrences"]}
        assert files == {"a.py", "b.py"}
        assert groups[0]["lines"] >= 8
        assert health["duplicates"]["duplicated_lines"] >= 8
        assert "compute_something" in groups[0]["snippet"]

    def test_long_duplicate_is_not_split_into_overlapping_groups(self, tmp_path):
        long_block = "\n".join(
            f"    step_{i} = transform_input_data(source_value_{i}, option_alpha_{i}, option_beta_{i})"
            for i in range(14)
        )
        write(tmp_path, "one.py", f"def one():\n{long_block}\n")
        write(tmp_path, "two.py", f"def two():\n{long_block}\n")
        health, _ = health_of(tmp_path)
        assert len(health["duplicates"]["items"]) == 1
        assert health["duplicates"]["items"][0]["lines"] >= 14

    def test_different_files_have_no_duplicates(self, tmp_path):
        write(tmp_path, "a.py", f"def alpha():\n{BLOCK}\n")
        other = BLOCK.replace("compute_something", "compute_other_thing")
        write(tmp_path, "b.py", f"def beta():\n{other}\n")
        health, _ = health_of(tmp_path)
        assert health["duplicates"]["items"] == []

    def test_import_blocks_and_short_lines_are_not_duplicates(self, tmp_path):
        imports = "\n".join(f"from package_{i}.module_name import something_{i}" for i in range(10))
        write(tmp_path, "a.py", imports + "\n")
        write(tmp_path, "b.py", imports + "\n")
        health, _ = health_of(tmp_path)
        assert health["duplicates"]["items"] == []


class TestHeatmap:
    def test_complex_file_ranks_first_and_is_hot(self, tmp_path):
        branches = "\n".join(f"    if value == {i}:\n        total += {i}" for i in range(30))
        write(tmp_path, "complex.py", f"def tangled(value):\n    total = 0\n{branches}\n    return total\n")
        write(tmp_path, "simple.py", "def tiny():\n    return 1\n")
        health, _ = health_of(tmp_path)
        files = health["heatmap"]["files"]
        assert [f["file"] for f in files][:2] == ["complex.py", "simple.py"]
        assert files[0]["score"] >= 50 and files[0]["level"] in ("alto", "crítico")
        assert files[1]["level"] == "bajo"
        assert files[0]["source"] == "ast" and files[0]["max_complexity"] > 10
        assert health["summary"]["hot_files"] == 1

    def test_non_python_complexity_is_marked_as_estimated(self, tmp_path):
        write(tmp_path, "main.js", "function f(a) {\n  if (a) { return 1; }\n  return 0;\n}\n")
        health, _ = health_of(tmp_path)
        entry = health["heatmap"]["files"][0]
        assert entry["source"] == "estimado" and entry["max_complexity"] is None

    def test_test_files_are_left_out_of_the_ranking(self, tmp_path):
        branches = "\n".join(f"    if v == {i}:\n        t += {i}" for i in range(30))
        write(tmp_path, "tests/test_big.py", f"def test_big(v):\n    t = 0\n{branches}\n")
        write(tmp_path, "src.py", "def visible():\n    return 1\n")
        health, _ = health_of(tmp_path)
        assert [f["file"] for f in health["heatmap"]["files"]] == ["src.py"]

    def test_ignored_directories_are_skipped(self, tmp_path):
        write(tmp_path, "node_modules/lib/index.js", "function hidden() { if (a) { return 1; } }\n")
        write(tmp_path, "src.py", "def visible():\n    return 1\n")
        health, _ = health_of(tmp_path)
        assert [f["file"] for f in health["heatmap"]["files"]] == ["src.py"]


class TestGeneral:
    def test_result_is_deterministic(self, tmp_path):
        write(tmp_path, "a.py", f"def alpha():\n{BLOCK}\n")
        write(tmp_path, "b.py", f"def beta():\n{BLOCK}\n")
        first, _ = health_of(tmp_path)
        second, _ = health_of(tmp_path)
        assert first == second

    def test_empty_project(self, tmp_path):
        health = analyze_code_health(tmp_path, {})
        assert health["summary"] == {"dead_code": 0, "duplicate_groups": 0,
                                     "duplicated_lines": 0, "hot_files": 0, "avg_heat": 0}

    def test_invalid_path_raises(self, tmp_path):
        with pytest.raises(ValueError):
            analyze_code_health(tmp_path / "does-not-exist", {})
