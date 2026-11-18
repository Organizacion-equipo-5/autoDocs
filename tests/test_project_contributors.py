from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import projects


def test_refresh_project_contributors_uses_connected_github_token(monkeypatch):
    project = {
        "_id": "project-1",
        "user_id": "user-1",
        "github_url": "https://github.com/acme/private-repo",
    }
    db = SimpleNamespace(
        projects=SimpleNamespace(
            find_one=lambda query: project,
            update_one=lambda *args, **kwargs: None,
        ),
        users=SimpleNamespace(
            find_one=lambda query: {"github": {"access_token": "oauth-token"}},
        ),
    )
    monkeypatch.setattr(projects, "get_db", lambda: db)
    calls = []

    def get_contributors(github_url, token=None):
        calls.append((github_url, token))
        return {
            "contributors": [{"username": "colleague", "commits": 3}],
            "total_commits": 3,
            "unique_authors": 1,
        }

    monkeypatch.setattr(
        "services.github_client.get_contributors_from_api",
        get_contributors,
    )

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-project-contributors",
    )
    JWTManager(app)
    app.register_blueprint(projects.projects_bp, url_prefix="/api/projects")
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().post(
        "/api/projects/project-1/contributors/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert calls == [("https://github.com/acme/private-repo", "oauth-token")]
    assert response.get_json()["contributors"][0]["username"] == "colleague"
