"""
tests/test_auth.py
Pruebas de autenticación.
"""
import pytest
from app import create_app
from app.config.settings import TestingConfig


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"


def test_registro_exitoso(client):
    res = client.post("/api/v1/auth/registro", json={
        "nombre": "Test", "apellido": "User",
        "email": "test@example.com",
        "password": "Test1234",
        "rol": "adulto",
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data["ok"] is True
    assert data["data"]["email"] == "test@example.com"


def test_registro_email_duplicado(client):
    payload = {
        "nombre": "Test", "apellido": "User",
        "email": "dup@example.com",
        "password": "Test1234", "rol": "adulto",
    }
    client.post("/api/v1/auth/registro", json=payload)
    res = client.post("/api/v1/auth/registro", json=payload)
    assert res.status_code == 400


def test_login_exitoso(client):
    client.post("/api/v1/auth/registro", json={
        "nombre": "Login", "apellido": "Test",
        "email": "login@example.com",
        "password": "Test1234", "rol": "adulto",
    })
    res = client.post("/api/v1/auth/login", json={
        "email": "login@example.com",
        "password": "Test1234",
    })
    assert res.status_code == 200
    data = res.get_json()
    assert "access_token" in data["data"]


def test_login_password_incorrecto(client):
    client.post("/api/v1/auth/registro", json={
        "nombre": "Bad", "apellido": "Pass",
        "email": "bad@example.com",
        "password": "Test1234", "rol": "adulto",
    })
    res = client.post("/api/v1/auth/login", json={
        "email": "bad@example.com", "password": "wrongpassword",
    })
    assert res.status_code == 401


def test_endpoint_protegido_sin_token(client):
    res = client.get("/api/v1/usuarios/me")
    assert res.status_code == 401
