from types import SimpleNamespace

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from routes import analysis


@pytest.mark.parametrize("status", ["pending", "analyzing", "error"])
def test_results_endpoint_does_not_return_stale_results_for_incomplete_analysis(
    monkeypatch, status
):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-analysis-status-tests",
    )
    JWTManager(app)
    app.register_blueprint(analysis.analysis_bp, url_prefix="/api/analysis")
    db = SimpleNamespace(
        projects=SimpleNamespace(
            find_one=lambda query: {"_id": "project-1", "status": status}
        ),
        analysis_results=SimpleNamespace(
            find_one=lambda query: {
                "results": {"old": True},
                "documentation": "stale documentation",
            }
        ),
    )
    monkeypatch.setattr(analysis, "get_db", lambda: db)
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().get(
        "/api/analysis/project-1/results",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"status": status, "results": None, "error": None}


def test_results_endpoint_returns_saved_results_when_project_is_completed(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-for-analysis-status-tests",
    )
    JWTManager(app)
    app.register_blueprint(analysis.analysis_bp, url_prefix="/api/analysis")
    result = {"results": {"new": True}, "documentation": "current documentation"}
    db = SimpleNamespace(
        projects=SimpleNamespace(
            find_one=lambda query: {"_id": "project-1", "status": "completed"}
        ),
        analysis_results=SimpleNamespace(find_one=lambda query: result),
    )
    monkeypatch.setattr(analysis, "get_db", lambda: db)
    with app.app_context():
        token = create_access_token(identity="user-1")

    response = app.test_client().get(
        "/api/analysis/project-1/results",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "completed",
        "results": {"new": True},
        "documentation": "current documentation",
    }
