from unittest.mock import patch

import pytest

from app import create_app


@pytest.fixture()
def client():
    with patch("app.init_db_indexes"):
        app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health_ok_cuando_mongo_responde(client):
    with patch("routes.monitoring._check_mongo", return_value=("up", 1.2)):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["checks"]["mongodb"]["status"] == "up"
    assert "uptime_seconds" in data


def test_health_503_cuando_mongo_cae(client):
    with patch("routes.monitoring._check_mongo", return_value=("down", 1500.0)):
        resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.get_json()["status"] == "degraded"


def test_metrics_formato_prometheus(client):
    client.get("/ruta-que-no-existe")  # genera un 404 medido
    resp = client.get("/metrics")
    assert resp.status_code == 200
    texto = resp.get_data(as_text=True)
    assert "autodocs_uptime_seconds" in texto
    assert 'autodocs_http_requests_total{method="GET",status="404"}' in texto
