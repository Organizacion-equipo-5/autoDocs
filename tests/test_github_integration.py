from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import github_integration


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
