from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import github_oauth


def _client(monkeypatch, user):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="test-secret-for-github-single-link")
    JWTManager(app)
    app.register_blueprint(github_oauth.github_oauth_bp, url_prefix="/api/github")
    monkeypatch.setattr(
        github_oauth,
        "get_db",
        lambda: SimpleNamespace(users=SimpleNamespace(find_one=lambda *args, **kwargs: user)),
    )
    monkeypatch.setattr(
        github_oauth,
        "_start_oauth",
        lambda **kwargs: ("state-123", "https://github.com/login/oauth/authorize?x=1"),
    )
    with app.app_context():
        token = create_access_token(identity="user-1")
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def test_connect_url_is_rejected_when_an_account_is_already_connected(monkeypatch):
    client, headers = _client(monkeypatch, {"github": {"id": 7, "login": "octocat"}})

    response = client.post("/api/github/connect-url", json={}, headers=headers)

    assert response.status_code == 409
    body = response.get_json()
    assert body["github_login"] == "octocat"
    assert "@octocat" in body["error"]


def test_connect_url_allows_reauthorizing_the_same_account(monkeypatch):
    client, headers = _client(monkeypatch, {"github": {"id": 7, "login": "octocat"}})

    response = client.post(
        "/api/github/connect-url", json={"reauthorize": True}, headers=headers
    )

    assert response.status_code == 200
    assert response.get_json()["url"].startswith("https://github.com/")


def test_connect_url_works_when_no_account_is_connected(monkeypatch):
    client, headers = _client(monkeypatch, {})

    response = client.post("/api/github/connect-url", json={}, headers=headers)

    assert response.status_code == 200


def test_status_reports_which_github_account_is_linked(monkeypatch):
    user = {
        "github": {
            "id": 7,
            "login": "octocat",
            "avatar_url": "https://avatars.githubusercontent.com/u/7",
            "scope": "read:user repo read:org",
        }
    }
    client, headers = _client(monkeypatch, user)

    body = client.get("/api/github/status", headers=headers).get_json()

    assert body["connected"] is True
    assert body["github_id"] == 7
    assert body["login"] == "octocat"
    assert body["avatar_url"].endswith("/u/7")
