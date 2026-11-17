import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import github_integration
from routes import insights


@pytest.fixture
def github_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-integration-tests-32-bytes",
        GITHUB_TOKEN="test-token",
    )
    JWTManager(app)
    app.register_blueprint(github_integration.github_bp, url_prefix="/api/integrations/github")

    project = {"github_url": "https://github.com/owner/repo"}
    db = SimpleNamespace(
        projects=SimpleNamespace(find_one=lambda query: project)
    )
    monkeypatch.setattr(github_integration, "get_db", lambda: db)
    monkeypatch.setattr(
        github_integration,
        "resolve_pair",
        lambda *args: (
            {"quality_score": 70, "totals": {}, "source": {}},
            {"quality_score": 80, "totals": {}, "source": {}},
        ),
    )
    with app.app_context():
        token = create_access_token(identity="user-1")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


@pytest.fixture
def github_webhook_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-integration-tests-32-bytes",
        GITHUB_WEBHOOK_SECRET="webhook-test-secret",
    )
    JWTManager(app)
    app.register_blueprint(github_integration.github_bp, url_prefix="/api/integrations/github")

    project = {
        "_id": "project-1",
        "github_url": "https://github.com/owner/repo",
        "file_path": "unused-by-mocked-worker",
    }

    class ActivityStore:
        def __init__(self):
            self.items = {}

        def update_one(self, query, update, upsert=False):
            activity_id = query["_id"]
            inserted_id = None
            if "$setOnInsert" in update and activity_id not in self.items:
                self.items[activity_id] = update["$setOnInsert"].copy()
                inserted_id = activity_id
            if "$set" in update and activity_id in self.items:
                self.items[activity_id].update(update["$set"])
            return SimpleNamespace(upserted_id=inserted_id)

    activity_store = ActivityStore()
    monkeypatch.setattr(
        github_integration,
        "get_db",
        lambda: SimpleNamespace(
            projects=SimpleNamespace(find=lambda query: [project]),
            github_activity=activity_store,
        ),
    )
    worker_calls = []
    monkeypatch.setattr(
        github_integration,
        "_start_activity_worker",
        lambda *args: worker_calls.append(args),
    )
    return app.test_client(), activity_store, worker_calls


def _response(status_code, payload):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_publish_report_creates_comment(github_client, monkeypatch):
    client, headers = github_client
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("get", url))
        if url.endswith("/pulls/7"):
            return _response(200, {})
        if url.endswith("/user"):
            return _response(200, {"login": "autodocs-bot"})
        return _response(200, [])

    def fake_post(url, **kwargs):
        calls.append(("post", url, kwargs["json"]["body"]))
        return _response(201, {"html_url": "https://github.com/owner/repo/pull/7#issuecomment-1"})

    monkeypatch.setattr(github_integration.requests, "get", fake_get)
    monkeypatch.setattr(github_integration.requests, "post", fake_post)
    monkeypatch.setattr(github_integration, "diff_snapshots", lambda *args: {})
    monkeypatch.setattr(github_integration, "render_pr_comment", lambda *args: "<!-- autodocs-quality-report -->\nreport")

    response = client.post(
        "/api/integrations/github/projects/project-1/pull-requests/7/report",
        headers=headers,
        json={},
    )

    assert response.status_code == 201
    assert response.get_json()["action"] == "created"
    assert calls[-1][0] == "post"
    assert "issues/7/comments" in calls[-1][1]


def test_publish_report_updates_only_bot_comment(github_client, monkeypatch):
    client, headers = github_client
    patch_call = {}

    def fake_get(url, **kwargs):
        if url.endswith("/pulls/7"):
            return _response(200, {})
        if url.endswith("/user"):
            return _response(200, {"login": "autodocs-bot"})
        return _response(200, [
            {
                "id": 13,
                "body": "<!-- autodocs-quality-report --> old",
                "user": {"login": "autodocs-bot"},
            },
            {
                "id": 14,
                "body": "<!-- autodocs-quality-report --> external",
                "user": {"login": "someone-else"},
            },
        ])

    def fake_patch(url, **kwargs):
        patch_call["url"] = url
        patch_call["body"] = kwargs["json"]["body"]
        return _response(200, {"html_url": "https://github.com/owner/repo/pull/7#issuecomment-13"})

    monkeypatch.setattr(github_integration.requests, "get", fake_get)
    monkeypatch.setattr(github_integration.requests, "patch", fake_patch)
    monkeypatch.setattr(github_integration, "diff_snapshots", lambda *args: {})
    monkeypatch.setattr(github_integration, "render_pr_comment", lambda *args: "new report")

    response = client.post(
        "/api/integrations/github/projects/project-1/pull-requests/7/report",
        headers=headers,
        json={},
    )

    assert response.status_code == 200
    assert response.get_json()["action"] == "updated"
    assert patch_call["url"].endswith("/issues/comments/13")
    assert patch_call["body"] == "new report"


def test_publish_report_requires_project_ownership(github_client, monkeypatch):
    client, headers = github_client
    monkeypatch.setattr(
        github_integration,
        "get_db",
        lambda: SimpleNamespace(
            projects=SimpleNamespace(find_one=lambda query: None)
        ),
    )
    monkeypatch.setattr(
        github_integration.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("GitHub should not be called"),
    )

    response = client.post(
        "/api/integrations/github/projects/project-1/pull-requests/7/report",
        headers=headers,
        json={},
    )

    assert response.status_code == 404


def _webhook_headers(body, event, delivery="delivery-1", signature_override=None):
    signature = "sha256=" + hmac.new(
        b"webhook-test-secret", body, hashlib.sha256
    ).hexdigest()
    return {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": signature_override or signature,
    }


def test_github_webhook_records_commit_and_starts_analysis(github_webhook_client):
    client, activities, worker_calls = github_webhook_client
    sha = "a" * 40
    payload = {
        "ref": "refs/heads/feature/new-report",
        "after": sha,
        "repository": {"html_url": "https://github.com/owner/repo"},
        "commits": [{
            "id": sha,
            "message": "Add quality report",
            "author": {"name": "Developer"},
            "timestamp": "2026-11-17T10:00:00Z",
        }],
    }
    body = json.dumps(payload).encode()

    response = client.post(
        "/api/integrations/github/webhook",
        data=body,
        content_type="application/json",
        headers=_webhook_headers(body, "push"),
    )

    assert response.status_code == 202
    assert response.get_json()["activities"] == 1
    activity = next(iter(activities.items.values()))
    assert activity["kind"] == "commit"
    assert activity["branch"] == "feature/new-report"
    assert activity["sha"] == sha
    assert activity["status"] == "pending"
    assert worker_calls[0][2:] == ("feature/new-report", sha, "push", [activity["_id"]])

    duplicate = client.post(
        "/api/integrations/github/webhook",
        data=body,
        content_type="application/json",
        headers=_webhook_headers(body, "push"),
    )
    assert duplicate.status_code == 202
    assert duplicate.get_json()["duplicate"] is True
    assert len(worker_calls) == 1


def test_github_webhook_records_branch_creation(github_webhook_client):
    client, activities, worker_calls = github_webhook_client
    payload = {
        "ref": "feature/new-branch",
        "ref_type": "branch",
        "repository": {"html_url": "https://github.com/owner/repo"},
        "sender": {"login": "developer"},
    }
    body = json.dumps(payload).encode()

    response = client.post(
        "/api/integrations/github/webhook",
        data=body,
        content_type="application/json",
        headers=_webhook_headers(body, "create"),
    )

    assert response.status_code == 202
    activity = next(iter(activities.items.values()))
    assert activity["kind"] == "branch"
    assert activity["branch"] == "feature/new-branch"
    assert activity["author"] == "developer"
    assert worker_calls[0][2:] == ("feature/new-branch", None, "create", [activity["_id"]])


def test_github_webhook_rejects_invalid_signature(github_webhook_client):
    client, activities, worker_calls = github_webhook_client
    body = json.dumps({"repository": {"html_url": "https://github.com/owner/repo"}}).encode()

    response = client.post(
        "/api/integrations/github/webhook",
        data=body,
        content_type="application/json",
        headers=_webhook_headers(body, "push", signature_override="sha256=invalid"),
    )

    assert response.status_code == 401
    assert activities.items == {}
    assert worker_calls == []


def test_github_activity_worker_checks_out_commit_and_runs_analysis(tmp_path, monkeypatch):
    sha = "b" * 40
    git_calls = []
    analysis_calls = []
    activity_updates = []

    def fake_run(command, **kwargs):
        git_calls.append(command)
        output = "refs/remotes/origin/main\n" if command[1] == "rev-parse" else ""
        if command[1] == "rev-parse" and command[2] == "refs/remotes/origin/main":
            output = sha + "\n"
        elif command[1] == "rev-parse":
            output = sha + "\n"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(github_integration.subprocess, "run", fake_run)

    def fake_analysis(project_id, project_path, db, source=None):
        analysis_calls.append((project_id, project_path, source))

    monkeypatch.setattr(github_integration, "run_analysis_async", fake_analysis)
    db = SimpleNamespace(
        github_activity=SimpleNamespace(
            update_many=lambda query, update: activity_updates.append(update["$set"])
        ),
        analysis_snapshots=SimpleNamespace(find_one=lambda query: None),
        projects=SimpleNamespace(find_one=lambda *args: {"status": "completed"}),
    )
    project = {"_id": "project-1", "file_path": str(tmp_path)}

    github_integration._process_github_activity(
        db, project, "main", sha, "push", ["activity-1"]
    )

    assert ["git", "checkout", "-B", "main", sha] in git_calls
    assert analysis_calls == [(
        "project-1",
        str(tmp_path),
        {"event": "push", "branch": "main", "sha": sha, "label": f"main@{sha[:7]}"},
    )]
    assert activity_updates[-1] == {"status": "completed"}


def test_project_activity_endpoint_returns_recent_events(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-integration-tests-32-bytes",
    )
    JWTManager(app)
    app.register_blueprint(insights.insights_bp, url_prefix="/api/insights")

    class ActivityCursor:
        def sort(self, key, direction):
            assert (key, direction) == ("occurred_at", -1)
            return self

        def limit(self, count):
            assert count == 100
            return self

        def __iter__(self):
            return iter([{
                "_id": "activity-1",
                "kind": "commit",
                "branch": "main",
                "sha": "c" * 40,
            }])

    monkeypatch.setattr(
        insights,
        "get_db",
        lambda: SimpleNamespace(
            projects=SimpleNamespace(find_one=lambda query: {"_id": "project-1"}),
            github_activity=SimpleNamespace(find=lambda query: ActivityCursor()),
        ),
    )
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().get(
        "/api/insights/project-1/activity",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["activities"][0]["id"] == "activity-1"
