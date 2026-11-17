"""
tests/test_github_ci.py

Pruebas de services/ci_report.py y scripts/autodocs_ci.py (GitHub Action).
Ejecutar con: python -m pytest tests/test_github_ci.py -v
"""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from services import analysis_history as ah
from services import ci_report
from services import code_health
from services.analyzer import ProjectAnalyzer

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("autodocs_ci", ROOT / "scripts" / "autodocs_ci.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")


def fn(name, file="app.py", complexity=1, doc=""):
    return {"name": name, "file": file, "line": 1, "params": [], "complexity": complexity, "docstring": doc}


def snap(score, functions=(), endpoints=(), sha=""):
    return ah.build_snapshot(
        {"quality_score": score, "functions": list(functions), "endpoints": list(endpoints),
         "classes": [], "issues": [], "complexity": {"avg": 1, "max": 1, "high_complexity_funcs": 0}},
        source={"sha": sha} if sha else None)


class TestPrComment:
    def test_comment_shows_score_change_and_new_items(self):
        base = snap(72, [fn("old")], sha="a" * 40)
        head = snap(65, [fn("old"), fn("tangled", complexity=14)],
                    [{"method": "POST", "path": "/api/new", "file": "routes/new.py"}], sha="b" * 40)
        body = ci_report.render_pr_comment(ah.diff_snapshots(base, head), head, base)
        assert body.startswith(ci_report.COMMENT_MARKER)
        assert "baja de **72** a **65** (-7)" in body
        assert "`POST /api/new`" in body
        assert "complejidad alta" in body and "`tangled`" in body
        assert "commit bbbbbbb vs aaaaaaa" in body

    def test_unchanged_pr(self):
        s = snap(80, [fn("a")])
        body = ci_report.render_pr_comment(ah.diff_snapshots(s, s), s, s)
        assert "se mantiene en **80**" in body and "no cambia funciones" in body

    def test_failed_gate_is_listed(self):
        s = snap(40)
        gate = {"failed": ["El score 40 es menor al mínimo (60)."]}
        body = ci_report.render_pr_comment(ah.diff_snapshots(s, s), s, s, gate)
        assert "Umbrales de calidad no cumplidos" in body and "menor al mínimo" in body

    def test_names_cannot_break_out_of_code_spans(self):
        base, head = snap(80), snap(80, [fn("evil`name<!--x", file="a|b.py")])
        body = ci_report.render_pr_comment(ah.diff_snapshots(base, head), head, base)
        assert "evil`name" not in body

    def test_project_report_escapes_table_cells(self):
        s = snap(90, endpoints=[{"method": "GET", "path": "/a|b", "file": "r.py"}])
        text = ci_report.render_project_report(s, project_name="demo")
        assert "# Documentación automática — demo" in text and "\\|" in text


class TestIgnores:
    def test_apply_ignores_filters_and_excludes_paths(self, monkeypatch):
        monkeypatch.setattr(ProjectAnalyzer, "IGNORE_DIRS", set(ProjectAnalyzer.IGNORE_DIRS))
        monkeypatch.setattr(code_health, "IGNORE_DIRS", set(code_health.IGNORE_DIRS))
        assert ci.apply_ignores("skipme, a/b ,,docs\\x") == {"skipme"}
        assert "skipme" in ProjectAnalyzer.IGNORE_DIRS and "skipme" in code_health.IGNORE_DIRS

    def test_ignored_folder_is_not_analyzed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ProjectAnalyzer, "IGNORE_DIRS", set(ProjectAnalyzer.IGNORE_DIRS))
        monkeypatch.setattr(code_health, "IGNORE_DIRS", set(code_health.IGNORE_DIRS))
        (tmp_path / "keep.py").write_text("def kept():\n    return 1\n")
        (tmp_path / "uploads").mkdir()
        (tmp_path / "uploads" / "other.py").write_text("def foreign():\n    return 1\n")
        ci.apply_ignores("uploads")
        snapshot, _ = ci.analyze_path(tmp_path)
        assert [f["name"] for f in snapshot["functions"]] == ["kept"]


class TestUpsertComment:
    def test_updates_existing_comment_or_creates_one(self, monkeypatch):
        calls = []

        def fake_api(method, url, token, body=None):
            calls.append((method, url))
            if method == "GET":
                return [{"id": 7, "body": "otro"}, {"id": 9, "body": ci_report.COMMENT_MARKER + " viejo"}]
            return {}

        monkeypatch.setattr(ci, "_api", fake_api)
        assert ci.upsert_pr_comment("o/r", 3, "tok", "nuevo") == "updated"
        assert calls[-1][0] == "PATCH" and calls[-1][1].endswith("/issues/comments/9")

        calls.clear()
        monkeypatch.setattr(ci, "_api", lambda m, u, t, b=None: [] if m == "GET" else calls.append((m, u)) or {})
        assert ci.upsert_pr_comment("o/r", 3, "tok", "nuevo") == "created"
        assert calls == [("POST", "https://api.github.com/repos/o/r/issues/3/comments")]


@needs_git
class TestPrCommand:
    @staticmethod
    def git(repo, *args):
        out = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                             cwd=repo, check=True, capture_output=True, text=True)
        return out.stdout.strip()

    @pytest.fixture
    def repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self.git(repo, "init", "-q", "-b", "main")
        (repo / "app.py").write_text('def helper():\n    """Ayuda."""\n    return 1\n')
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-q", "-m", "base")
        base = self.git(repo, "rev-parse", "HEAD")
        (repo / "api.py").write_text(
            "from flask import Blueprint\nbp = Blueprint('x', __name__)\n\n"
            "@bp.route('/health', methods=['GET'])\ndef health():\n    return 'ok'\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-q", "-m", "head")
        return repo, base, self.git(repo, "rev-parse", "HEAD")

    def run_pr(self, repo, base, head, tmp_path, monkeypatch, *extra):
        out, summary = tmp_path / "gh_output", tmp_path / "gh_summary"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
        monkeypatch.setattr(ProjectAnalyzer, "IGNORE_DIRS", set(ProjectAnalyzer.IGNORE_DIRS))
        monkeypatch.setattr(code_health, "IGNORE_DIRS", set(code_health.IGNORE_DIRS))
        code = ci.main(["pr", "--path", str(repo), "--base-sha", base, "--head-sha", head,
                        "--no-comment", "--diff-out", str(tmp_path / "diff.json"), *extra])
        return code, out, summary

    def test_compares_base_and_head(self, repo, tmp_path, monkeypatch):
        repo_dir, base, head = repo
        code, out, summary = self.run_pr(repo_dir, base, head, tmp_path, monkeypatch)
        assert code == 0
        outputs = dict(line.split("=", 1) for line in out.read_text().splitlines())
        assert {"score", "base_score", "delta"} <= set(outputs)
        assert ci_report.COMMENT_MARKER in summary.read_text()
        diff = json.loads((tmp_path / "diff.json").read_text())
        assert [e["path"] for e in diff["endpoints"]["added"]] == ["/health"]
        assert [f["name"] for f in diff["functions"]["added"]] == ["health"]

    def test_quality_gate_fails_the_job(self, repo, tmp_path, monkeypatch, capsys):
        repo_dir, base, head = repo
        code, _, summary = self.run_pr(repo_dir, base, head, tmp_path, monkeypatch, "--fail-under", "101")
        assert code == 1
        assert "::error::" in capsys.readouterr().out
        assert "Umbrales de calidad no cumplidos" in summary.read_text()

    def test_unknown_base_commit_is_a_clear_error(self, repo, tmp_path, monkeypatch, capsys):
        repo_dir, _, head = repo
        code, _, _ = self.run_pr(repo_dir, "0" * 40, head, tmp_path, monkeypatch)
        assert code == 2 and "fetch-depth: 0" in capsys.readouterr().out

    def test_missing_base_without_pr_event(self, repo, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
        assert ci.main(["pr", "--path", str(repo[0]), "--no-comment"]) == 2
        assert "commit base" in capsys.readouterr().out
