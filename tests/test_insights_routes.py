"""
tests/test_insights_routes.py

Pruebas de routes/insights.py, routes/github_integration.py y del guardado de
snapshots en routes/analysis.run_analysis_async, con MongoDB simulado (mongomock).
No se usa create_app() para no abrir conexiones reales.
Ejecutar con: python -m pytest tests/test_insights_routes.py -v
"""
import hashlib
import hmac
import json
import shutil
import subprocess
import threading
from datetime import datetime

import mongomock
import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

import routes.github_integration as gh
import routes.insights as insights
from services import analysis_history as ah

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")
SECRET = "webhook-secret-for-tests"


@pytest.fixture
def env(monkeypatch, tmp_path):
    db = mongomock.MongoClient().db
    app = Flask(__name__)
    app.config.update(JWT_SECRET_KEY="test-secret-key-long-enough-to-be-valid-123", TESTING=True)
    JWTManager(app)
    monkeypatch.setattr(insights, "get_db", lambda: db)
    monkeypatch.setattr(gh, "get_db", lambda: db)
    monkeypatch.chdir(tmp_path)
    insights._INDEX_CACHE.clear()
    app.register_blueprint(insights.insights_bp, url_prefix="/api/insights")
    app.register_blueprint(gh.github_bp, url_prefix="/api/integrations/github")
    with app.app_context():
        token = create_access_token(identity="user1")
    return app.test_client(), db, {"Authorization": f"Bearer {token}"}


def add_project(db, pid="p1", user="user1", **extra):
    db.projects.insert_one({"_id": pid, "user_id": user, "name": pid, "status": "completed", **extra})


RESULTS = {
    "quality_score": 70, "total_files": 2, "primary_language": "Python", "issues": [], "structure": [],
    "functions": [{"name": "login_user", "file": "routes/auth.py", "line": 20, "params": ["email"],
                   "docstring": "Valida las credenciales.", "complexity": 3}],
    "classes": [], "endpoints": [{"method": "POST", "path": "/api/auth/login", "file": "routes/auth.py"}],
    "complexity": {"avg": 3, "max": 3, "high_complexity_funcs": 0},
}


def add_analysis(db, pid="p1", results=None):
    db.analysis_results.insert_one({"project_id": pid, "results": results or RESULTS,
                                    "documentation": {"full_markdown": "## Calidad\nTexto."},
                                    "created_at": "2026-01-01T00:00:00"})


# ─────────────────────────── /health ───────────────────────────
class TestHealthRoute:
    def test_requires_auth_and_ownership(self, env):
        client, db, headers = env
        add_project(db, "other", user="someone-else")
        assert client.get("/api/insights/p1/health").status_code == 401
        assert client.get("/api/insights/other/health", headers=headers).status_code == 404

    def test_not_available_before_analysis(self, env):
        client, db, headers = env
        add_project(db)
        data = client.get("/api/insights/p1/health", headers=headers).get_json()
        assert data["available"] is False

    def test_returns_stored_health(self, env):
        client, db, headers = env
        add_project(db)
        add_analysis(db, results={**RESULTS, "code_health": {"summary": {"dead_code": 1}}})
        data = client.get("/api/insights/p1/health", headers=headers).get_json()
        assert data["available"] is True and data["health"]["summary"]["dead_code"] == 1

    def test_computes_on_the_fly_for_old_analyses_and_stores_it(self, env, tmp_path):
        client, db, headers = env
        src = tmp_path / "uploads" / "p1" / "src"
        src.mkdir(parents=True)
        (src / "app.py").write_text("def orphan_function():\n    return 1\n")
        add_project(db, file_path=str(src))
        add_analysis(db)
        data = client.get("/api/insights/p1/health", headers=headers).get_json()
        assert data["available"] is True
        assert [d["name"] for d in data["health"]["dead_code"]["items"]] == ["orphan_function"]
        assert "code_health" in db.analysis_results.find_one({"project_id": "p1"})["results"]

    def test_empty_file_path_never_scans_the_app_directory(self, env, tmp_path):
        """Regresión: Path('') == Path('.') escaneaba el directorio de la aplicación."""
        client, db, headers = env
        (tmp_path / "config.py").write_text("SECRET = 'do-not-leak'\n\ndef leaked_function():\n    return 1\n")
        add_project(db, file_path="")
        add_analysis(db)
        data = client.get("/api/insights/p1/health", headers=headers).get_json()
        assert data["available"] is False
        assert "leaked_function" not in json.dumps(data) and "do-not-leak" not in json.dumps(data)

    def test_paths_outside_uploads_are_rejected(self, env, tmp_path):
        client, db, headers = env
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "x.py").write_text("def outside_fn():\n    return 1\n")
        add_project(db, file_path=str(outside))
        add_analysis(db)
        assert client.get("/api/insights/p1/health", headers=headers).get_json()["available"] is False


# ─────────────────── /history y /compare ───────────────────
class TestHistoryAndCompare:
    def seed(self, db):
        ids = []
        for i, score in enumerate((60, 75)):
            functions = RESULTS["functions"] * (i + 1)
            sid = ah.save_snapshot(db, "p1", {**RESULTS, "quality_score": score, "functions": functions})
            db.analysis_history.update_one({"_id": sid}, {"$set": {"created_at": f"2026-01-0{i + 1}T00:00:00"}})
            ids.append(sid)
        return ids

    def test_history_returns_trend(self, env):
        client, db, headers = env
        add_project(db)
        self.seed(db)
        data = client.get("/api/insights/p1/history", headers=headers).get_json()
        assert [p["quality_score"] for p in data["snapshots"]] == [60, 75] and data["count"] == 2

    def test_compare_defaults_to_last_two_and_accepts_ids(self, env):
        client, db, headers = env
        add_project(db)
        ids = self.seed(db)
        data = client.get("/api/insights/p1/compare", headers=headers).get_json()
        assert data["diff"]["score"]["delta"] == 15 and (data["from_id"], data["to_id"]) == tuple(ids)
        data = client.get(f"/api/insights/p1/compare?from={ids[0]}&to={ids[1]}", headers=headers).get_json()
        assert data["diff"]["score"]["old"] == 60

    def test_compare_errors(self, env):
        client, db, headers = env
        add_project(db)
        res = client.get("/api/insights/p1/compare", headers=headers)
        assert res.status_code == 404 and "al menos dos" in res.get_json()["error"]
        self.seed(db)
        assert client.get("/api/insights/p1/compare?from=nope&to=nada", headers=headers).status_code == 404


# ─────────────────────────── /chat ───────────────────────────
class FakeAIEnhancer:
    def is_available(self):
        return True

    def _call_ai(self, system, user, max_tokens=400):
        return "La validación está en routes/auth.py"


class TestChatRoute:
    def test_validation_and_state_errors(self, env):
        client, db, headers = env
        add_project(db)
        assert client.post("/api/insights/p1/chat", json={"question": "x"}).status_code == 401
        assert client.post("/api/insights/p1/chat", headers=headers, json={"question": " "}).status_code == 400
        assert client.post("/api/insights/p1/chat", headers=headers, json={"question": "login"}).status_code == 409
        assert client.post("/api/insights/nope/chat", headers=headers, json={"question": "login"}).status_code == 404

    def test_free_plan_gets_extractive_answers(self, env, monkeypatch):
        client, db, headers = env
        add_project(db)
        add_analysis(db)
        db.users.insert_one({"_id": "user1", "plan": "free"})
        monkeypatch.setattr(insights, "AIEnhancer", lambda: pytest.fail("no debe usar IA en plan free"))
        data = client.post("/api/insights/p1/chat", headers=headers,
                           json={"question": "¿dónde se valida el login?"}).get_json()
        assert data["mode"] == "extractive" and data["ai_available_in_plan"] is False
        assert data["sources"][0]["file"] == "routes/auth.py"
        assert db.usage_logs.count_documents({"user_id": "user1", "action": "doc_chat"}) == 1

    def test_pro_plan_uses_ai(self, env, monkeypatch):
        client, db, headers = env
        add_project(db)
        add_analysis(db)
        db.users.insert_one({"_id": "user1", "plan": "pro"})
        monkeypatch.setattr(insights, "AIEnhancer", FakeAIEnhancer)
        data = client.post("/api/insights/p1/chat", headers=headers, json={"question": "login"}).get_json()
        assert data["mode"] == "ai" and data["ai_available_in_plan"] is True
        assert "routes/auth.py" in data["answer"]

    def test_hourly_limit(self, env):
        client, db, headers = env
        add_project(db)
        add_analysis(db)
        now = datetime.utcnow().isoformat()
        db.usage_logs.insert_many([{"user_id": "user1", "action": "doc_chat", "created_at": now}
                                   for _ in range(insights.CHAT_LIMIT_PER_HOUR)])
        res = client.post("/api/insights/p1/chat", headers=headers, json={"question": "login"})
        assert res.status_code == 429


# ─────────────────────────── webhook ───────────────────────────
def signed(payload, secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, sig


def push_payload(**over):
    payload = {"ref": "refs/heads/main", "after": "a" * 40,
               "repository": {"full_name": "Acme/Widgets", "default_branch": "main"},
               "head_commit": {"message": "feat: algo\n\ncuerpo"}, "pusher": {"name": "ana"}}
    payload.update(over)
    return payload


def post_event(client, payload, event="push", secret=SECRET, sig=None):
    body, good = signed(payload, secret)
    return client.post("/api/integrations/github/webhook", data=body, content_type="application/json",
                       headers={"X-GitHub-Event": event, "X-Hub-Signature-256": sig or good})


class TestWebhook:
    @pytest.fixture(autouse=True)
    def secret(self, monkeypatch):
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)

    def test_signature_helper(self):
        body = b"{}"
        good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
        assert gh.verify_signature("s", body, good)
        assert not gh.verify_signature("s", body, "sha256=00")
        assert not gh.verify_signature("s", body, "")
        assert not gh.verify_signature("", body, good)
        assert not gh.verify_signature("s", body, good.replace("sha256=", "sha1="))

    def test_unconfigured_secret_rejects_everything(self, env, monkeypatch):
        client, _, _ = env
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET")
        assert post_event(client, push_payload()).status_code == 503

    def test_bad_signature_is_rejected(self, env):
        client, _, _ = env
        assert post_event(client, push_payload(), sig="sha256=" + "0" * 64).status_code == 401
        assert post_event(client, push_payload(), secret="otro-secreto").status_code == 401

    def test_ping_and_ignored_events(self, env):
        client, _, _ = env
        assert post_event(client, {"zen": "hola"}, event="ping").get_json() == {"message": "pong"}
        assert post_event(client, {"action": "opened"}, event="pull_request").status_code == 202

    def test_only_default_branch_pushes_are_processed(self, env):
        client, _, _ = env
        assert post_event(client, push_payload(ref="refs/heads/feature")).status_code == 202
        assert post_event(client, push_payload(deleted=True)).status_code == 202
        for repo in ({"full_name": "../etc", "default_branch": "main"},
                     {"full_name": "a/b", "default_branch": "--upload-pack=x"}):
            assert post_event(client, push_payload(repository=repo)).status_code == 400

    def test_push_regenerates_matching_projects(self, env, monkeypatch):
        client, db, _ = env
        db.users.insert_many([{"_id": "free-user", "plan": "free"}, {"_id": "pro-user", "plan": "pro"}])
        add_project(db, "match", user="pro-user", github_url="https://github.com/acme/widgets.git")
        add_project(db, "busy", user="pro-user", github_url="https://github.com/Acme/Widgets", status="analyzing")
        add_project(db, "unrelated", user="pro-user", github_url="https://github.com/acme/widgets-extra")
        add_project(db, "capped", user="free-user", github_url="https://github.com/ACME/WIDGETS/")
        month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        db.analysis_results.insert_many([{"project_id": "capped", "created_at": month} for _ in range(10)])

        done, seen = threading.Event(), {}

        def fake_regenerate(_db, project, branch, source):
            seen.update(project_id=project["_id"], branch=branch, source=source)
            done.set()

        monkeypatch.setattr(gh, "_regenerate", fake_regenerate)
        data = post_event(client, push_payload()).get_json()
        assert data["started"] == ["match"]
        assert {s["project_id"] for s in data["skipped"]} == {"busy", "capped"}
        assert done.wait(5)
        assert seen["branch"] == "main"
        assert seen["source"] == {"event": "push", "sha": "a" * 40, "branch": "main", "message": "feat: algo",
                                  "repo": "Acme/Widgets", "actor": "ana"}

    def test_regenerate_marks_project_as_error_when_sync_fails(self, env, monkeypatch):
        _, db, _ = env
        add_project(db, "p1", github_url="https://github.com/acme/widgets")
        monkeypatch.setattr(gh, "_sync_repository", lambda p, b: (_ for _ in ()).throw(RuntimeError("sin red")))
        gh._regenerate(db, db.projects.find_one({"_id": "p1"}), "main", {})
        project = db.projects.find_one({"_id": "p1"})
        assert project["status"] == "error" and "sin red" in project["error_message"]

    @needs_git
    def test_sync_repository_fast_forwards_an_existing_clone(self, tmp_path):
        def git(cwd, *args):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                           cwd=cwd, check=True, capture_output=True)

        origin, clone = tmp_path / "origin", tmp_path / "clone"
        origin.mkdir()
        git(origin, "init", "-q", "-b", "main")
        (origin / "a.py").write_text("v = 1\n")
        git(origin, "add", ".")
        git(origin, "commit", "-q", "-m", "1")
        git(tmp_path, "clone", "-q", str(origin), str(clone))
        (origin / "b.py").write_text("v = 2\n")
        git(origin, "add", ".")
        git(origin, "commit", "-q", "-m", "2")

        path = gh._sync_repository({"_id": "p1", "file_path": str(clone), "github_url": str(origin)}, "main")
        assert (clone / "b.py").exists() and path == str(clone.resolve())


# ───────────── run_analysis_async guarda el snapshot ─────────────
class TestRunAnalysisSnapshot:
    def test_analysis_stores_code_health_and_history(self, env, monkeypatch, tmp_path):
        import routes.analysis as analysis

        class FakeEnhancer:
            def is_available(self):
                return False

            def mine_code_patterns(self, results):
                return {}

            def enhance_documentation(self, results):
                return results

        class FakeDocGen:
            def __init__(self, results):
                pass

            def generate(self):
                return {"full_markdown": "# doc"}

        monkeypatch.setattr(analysis, "AIEnhancer", FakeEnhancer)
        monkeypatch.setattr(analysis, "DocGenerator", FakeDocGen)
        _, db, _ = env
        project = tmp_path / "proj"
        project.mkdir()
        (project / "app.py").write_text("def orphan_function():\n    return 1\n")
        add_project(db, "p1", status="pending")

        analysis.run_analysis_async("p1", str(project), db, source={"event": "push", "sha": "abc1234"})

        stored = db.analysis_results.find_one({"project_id": "p1"})
        assert stored["results"]["code_health"]["summary"]["dead_code"] == 1
        snapshots = ah.list_snapshots(db, "p1")
        assert len(snapshots) == 1 and snapshots[0]["source"]["sha"] == "abc1234"
        assert db.projects.find_one({"_id": "p1"})["status"] == "completed"

    def test_snapshot_failure_does_not_break_the_analysis(self, env, monkeypatch, tmp_path):
        import routes.analysis as analysis

        class FakeEnhancer:
            def is_available(self):
                return False

            def mine_code_patterns(self, results):
                return {}

            def enhance_documentation(self, results):
                return results

        monkeypatch.setattr(analysis, "AIEnhancer", FakeEnhancer)
        monkeypatch.setattr(analysis, "DocGenerator", lambda r: type("D", (), {"generate": lambda s: {}})())
        monkeypatch.setattr(analysis, "save_snapshot", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db caída")))
        _, db, _ = env
        (tmp_path / "p").mkdir()
        (tmp_path / "p" / "a.py").write_text("x = 1\n")
        add_project(db, "p1", status="pending")
        analysis.run_analysis_async("p1", str(tmp_path / "p"), db)
        assert db.projects.find_one({"_id": "p1"})["status"] == "completed"
