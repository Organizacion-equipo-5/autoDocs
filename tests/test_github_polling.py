from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import github_integration


@pytest.fixture
def github_polling_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-polling-tests",
    )
    JWTManager(app)
    app.register_blueprint(
        github_integration.github_bp,
        url_prefix="/api/integrations/github",
    )
    with app.app_context():
        token = create_access_token(identity="user-1")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _db_for(project):
    return SimpleNamespace(
        projects=SimpleNamespace(
            find_one=lambda query: project,
            update_one=lambda *args, **kwargs: SimpleNamespace(modified_count=1),
        ),
        users=SimpleNamespace(find_one=lambda query: {"plan": "pro"}),
    )


class _ApiResponse:
    def __init__(self, data, status_code=200, headers=None):
        self.data = data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"GitHub API returned {self.status_code}")


def test_get_project_branches_returns_branch_names_and_selection(
    github_polling_client, monkeypatch
):
    client, headers = github_polling_client
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/owner/repo",
        "github_branch": "feature/selected",
    }
    monkeypatch.setattr(
        github_integration,
        "get_db",
        lambda: _db_for(project),
    )
    responses = iter([
        _ApiResponse({"default_branch": "main"}),
        _ApiResponse([{"name": "main"}, {"name": "feature/selected"}]),
    ])
    monkeypatch.setattr(
        github_integration.requests,
        "get",
        lambda *args, **kwargs: next(responses),
    )

    response = client.get(
        "/api/integrations/github/projects/project-1/branches",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "branches": ["main", "feature/selected"],
        "selected": "feature/selected",
    }


def test_poll_queues_analysis_when_selected_branch_sha_changes(
    github_polling_client, monkeypatch
):
    client, headers = github_polling_client
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/owner/repo",
        "github_branch": "main",
        "github_sha": "a" * 40,
        "file_path": None,
    }
    queued = []
    monkeypatch.setattr(github_integration, "get_db", lambda: _db_for(project))
    monkeypatch.setattr(
        github_integration,
        "_github_branch_data",
        lambda *args: {"name": "main", "sha": "b" * 40},
    )
    monkeypatch.setattr(
        github_integration,
        "_queue_branch_analysis",
        lambda *args, **kwargs: queued.append((args, kwargs)) or "queued",
    )

    response = client.post(
        "/api/integrations/github/projects/project-1/poll",
        headers=headers,
    )

    assert response.status_code == 202
    assert response.get_json() == {"branch": "main", "status": "queued"}
    assert queued[0][0][2:5] == ("main", "b" * 40, "poll")


def test_select_project_branch_queues_selected_branch_analysis(
    github_polling_client, monkeypatch
):
    client, headers = github_polling_client
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/owner/repo",
        "file_path": "unused",
    }
    queued = []
    monkeypatch.setattr(github_integration, "get_db", lambda: _db_for(project))
    monkeypatch.setattr(
        github_integration,
        "_github_branch_data",
        lambda *args: {"name": "feature/new", "sha": "c" * 40},
    )
    monkeypatch.setattr(
        github_integration,
        "_queue_branch_analysis",
        lambda *args, **kwargs: queued.append((args, kwargs)) or "queued",
    )

    response = client.post(
        "/api/integrations/github/projects/project-1/branch",
        headers={**headers, "Content-Type": "application/json"},
        json={"branch": "feature/new"},
    )

    assert response.status_code == 202
    assert response.get_json()["branch"] == "feature/new"
    assert queued[0][0][2:5] == ("feature/new", "c" * 40, "branch_switch")
    assert queued[0][1] == {"force": True, "etag": None}


def test_poll_uses_etag_and_skips_unchanged_branch(github_polling_client, monkeypatch):
    client, headers = github_polling_client
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/owner/repo",
        "github_branch": "main",
        "github_etag": '"branch-etag"',
        "github_sha": "a" * 40,
        "file_path": None,
    }
    request_headers = []
    monkeypatch.setattr(github_integration, "get_db", lambda: _db_for(project))
    monkeypatch.setattr(
        github_integration.requests,
        "get",
        lambda url, **kwargs: (
            request_headers.append(kwargs["headers"])
            or _ApiResponse(None, status_code=304)
        ),
    )

    response = client.post(
        "/api/integrations/github/projects/project-1/poll",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {"branch": "main", "status": "unchanged"}
    assert request_headers[0]["If-None-Match"] == '"branch-etag"'
