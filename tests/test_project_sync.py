from pathlib import Path
from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import projects


def test_sync_reclones_repository_when_saved_path_is_missing(monkeypatch, tmp_path):
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/owner/repo",
        "file_path": str(tmp_path / "old-deployment" / "repo"),
    }
    updates = []
    db = SimpleNamespace(
        users=SimpleNamespace(find_one=lambda query: {"plan": "pro"}),
        projects=SimpleNamespace(
            find_one=lambda query: project,
            update_one=lambda query, update: updates.append((query, update)),
        ),
    )
    cloned_path = tmp_path / "uploads" / "project-1" / "repo"
    cloned_path.mkdir(parents=True)
    clone_calls = []
    monkeypatch.setattr(projects, "get_db", lambda: db)
    monkeypatch.setattr(
        projects,
        "clone_github_repo",
        lambda url, project_id: clone_calls.append((url, project_id)) or str(cloned_path),
    )
    monkeypatch.setattr(
        projects.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )
    monkeypatch.setattr(projects.requests, "post", lambda *args, **kwargs: None)

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-project-sync-tests",
    )
    JWTManager(app)
    app.register_blueprint(projects.projects_bp, url_prefix="/api/projects")
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().post(
        "/api/projects/project-1/sync",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert clone_calls == [("https://github.com/owner/repo", "project-1")]
    assert ({"_id": "project-1"}, {"$set": {"file_path": str(cloned_path)}}) in updates
    assert any(update["$set"].get("status") == "pending" for _, update in updates)
