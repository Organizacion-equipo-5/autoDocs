from types import SimpleNamespace

from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import github_oauth


class _ApiResponse:
    status_code = 200

    def __init__(self, repos):
        self.repos = repos

    def json(self):
        return self.repos


def _repo(full_name):
    owner, name = full_name.split("/")
    return {
        "full_name": full_name,
        "name": name,
        "private": True,
        "html_url": f"https://github.com/{full_name}",
        "owner": {"login": owner, "type": "Organization"},
    }


def test_oauth_scope_always_includes_read_org(monkeypatch):
    monkeypatch.setenv("GITHUB_OAUTH_SCOPE", "read:user repo")

    assert "read:org" in github_oauth._cfg()["scope"].split()


def test_github_status_reports_whether_org_scope_was_granted(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-oauth-repos",
    )
    JWTManager(app)
    app.register_blueprint(github_oauth.github_oauth_bp, url_prefix="/api/github")
    user = {"github": {"login": "octocat", "scope": "read:user,repo"}}
    monkeypatch.setattr(
        github_oauth,
        "get_db",
        lambda: SimpleNamespace(users=SimpleNamespace(find_one=lambda *args: user)),
    )
    with app.app_context():
        token = create_access_token(identity="user-1")
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    response_without_scope = client.get("/api/github/status", headers=headers)
    user["github"]["scope"] = "read:user,repo,read:org"
    response_with_scope = client.get("/api/github/status", headers=headers)

    assert response_without_scope.get_json()["organization_access"] is False
    assert response_with_scope.get_json()["organization_access"] is True


def test_github_repos_includes_organization_repos_across_pages(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-github-oauth-repos",
    )
    JWTManager(app)
    app.register_blueprint(github_oauth.github_oauth_bp, url_prefix="/api/github")
    db = SimpleNamespace(
        users=SimpleNamespace(
            find_one=lambda query, *args: {
                "github": {"access_token": "oauth-token"},
            },
        )
    )
    monkeypatch.setattr(github_oauth, "get_db", lambda: db)
    requests_seen = []

    def fake_get(url, **kwargs):
        requests_seen.append((url, kwargs))
        page = kwargs["params"]["page"]
        if url.endswith("/user/repos") and page == 1:
            return _ApiResponse([_repo(f"personal/repo-{index}") for index in range(100)])
        if url.endswith("/user/repos"):
            return _ApiResponse([])
        if url.endswith("/user/orgs"):
            return _ApiResponse([{"login": "acme", "avatar_url": "https://github.com/acme.png"}])
        if url.endswith("/orgs/acme/repos"):
            return _ApiResponse([_repo("acme/repository")])
        raise AssertionError(f"Unexpected GitHub API URL: {url}")

    monkeypatch.setattr(github_oauth.requests, "get", fake_get)
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().get(
        "/api/github/repos",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    repos = response.get_json()
    assert len(repos) == 101
    assert any(repo["full_name"] == "acme/repository" for repo in repos)
    user_repo_requests = [
        call for call in requests_seen if call[0].endswith("/user/repos")
    ]
    assert [call[1]["params"]["page"] for call in user_repo_requests] == [1, 2]
    assert all(call[1]["params"]["affiliation"]
               == "owner,collaborator,organization_member"
               for call in user_repo_requests)
    assert any(call[0].endswith("/orgs/acme/repos") for call in requests_seen)
    assert all(
        call[1]["headers"]["Authorization"] == "Bearer oauth-token"
        for call in requests_seen
    )

    organizations_response = app.test_client().get(
        "/api/github/organizations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert organizations_response.status_code == 200
    assert organizations_response.get_json() == [{
        "login": "acme",
        "avatar_url": "https://github.com/acme.png",
        "html_url": "https://github.com/acme",
    }]
