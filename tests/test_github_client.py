"""
tests/test_github_client.py

Tests unitarios para services/github_client.py
Ejecutar con: python -m pytest tests/test_github_client.py -v
"""

import pytest
import requests
from unittest.mock import patch, MagicMock

from services.github_client import (
    extract_repo_info,
    get_contributors_from_api,
    _estimate_active_days,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 200, json_data=None, raise_exc=None):
    """Crea un MagicMock que simula una respuesta de requests.get."""
    if raise_exc:
        raise raise_exc
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data if json_data is not None else []
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Tests: extract_repo_info
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractRepoInfo:
    def test_url_https_simple(self):
        owner, repo = extract_repo_info("https://github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_con_punto_git(self):
        owner, repo = extract_repo_info("https://github.com/octocat/Hello-World.git")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_sin_protocolo(self):
        owner, repo = extract_repo_info("github.com/octocat/Hello-World")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_con_slash_final(self):
        owner, repo = extract_repo_info("https://github.com/octocat/Hello-World/")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_con_query_string(self):
        owner, repo = extract_repo_info("https://github.com/octocat/Hello-World?tab=readme")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_ssh(self):
        # Formato git@github.com:owner/repo.git
        owner, repo = extract_repo_info("git@github.com:octocat/Hello-World.git")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_con_espacios_se_recorta(self):
        owner, repo = extract_repo_info("  https://github.com/octocat/Hello-World  ")
        assert owner == "octocat"
        assert repo == "Hello-World"

    def test_url_invalida_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            extract_repo_info("https://gitlab.com/octocat/repo")
        assert "No se pudo extraer" in str(exc.value)

    def test_string_vacio_lanza_error(self):
        with pytest.raises(ValueError):
            extract_repo_info("")

    def test_repo_con_guiones_y_numeros(self):
        owner, repo = extract_repo_info("https://github.com/my-org-123/my-repo-456")
        assert owner == "my-org-123"
        assert repo == "my-repo-456"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: get_contributors_from_api
# ─────────────────────────────────────────────────────────────────────────────

class TestGetContributorsFromApi:
    @patch("services.github_client._estimate_active_days", return_value=30)
    @patch("services.github_client.requests.get")
    def test_respuesta_exitosa(self, mock_get, mock_days):
        mock_get.return_value = _mock_response(200, [
            {"login": "alice", "avatar_url": "https://a.com/alice.png", "contributions": 100},
            {"login": "bob", "avatar_url": "https://a.com/bob.png", "contributions": 50},
            {"login": "charlie", "avatar_url": "https://a.com/charlie.png", "contributions": 20},
        ])

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert len(result["contributors"]) == 3
        assert result["total_commits"] == 170
        assert result["unique_authors"] == 3
        assert result["active_days"] == 30
        assert result["repo_url"] == "https://github.com/owner/repo"
        assert result["repo_name"] == "owner/repo"

    @patch("services.github_client._estimate_active_days", return_value=10)
    @patch("services.github_client.requests.get")
    def test_ordenamiento_por_commits(self, mock_get, mock_days):
        # Deliberadamente desordenados
        mock_get.return_value = _mock_response(200, [
            {"login": "charlie", "avatar_url": "", "contributions": 5},
            {"login": "alice", "avatar_url": "", "contributions": 100},
            {"login": "bob", "avatar_url": "", "contributions": 50},
        ])

        result = get_contributors_from_api("https://github.com/owner/repo")

        # Debe estar ordenado de mayor a menor
        assert result["contributors"][0]["username"] == "alice"
        assert result["contributors"][1]["username"] == "bob"
        assert result["contributors"][2]["username"] == "charlie"

    @patch("services.github_client.requests.get")
    def test_repositorio_no_encontrado_404(self, mock_get):
        mock_get.return_value = _mock_response(404, {})

        result = get_contributors_from_api("https://github.com/owner/no-existe")

        assert result["contributors"] == []
        assert "no encontrado" in result["message"].lower()
        assert "owner/no-existe" in result["message"]

    @patch("services.github_client.requests.get")
    def test_rate_limit_403(self, mock_get):
        mock_get.return_value = _mock_response(403, {})

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert result["contributors"] == []
        assert "límite" in result["message"].lower() or "limite" in result["message"].lower()

    @patch("services.github_client.requests.get")
    def test_error_500_lanza_excepcion(self, mock_get):
        mock_get.return_value = _mock_response(500, {})

        with pytest.raises(Exception) as exc:
            get_contributors_from_api("https://github.com/owner/repo")
        assert "GitHub API" in str(exc.value) or "500" in str(exc.value)

    @patch("services.github_client.requests.get")
    def test_respuesta_con_mensaje_de_error(self, mock_get):
        # GitHub devuelve 200 pero con dict de error
        mock_get.return_value = _mock_response(200, {"message": "API rate limit exceeded"})

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert result["contributors"] == []
        assert "rate limit" in result["message"].lower() or "API" in result["message"]

    @patch("services.github_client.requests.get")
    def test_lista_vacia_de_contributors(self, mock_get):
        mock_get.return_value = _mock_response(200, [])

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert result["contributors"] == []
        assert "no se encontraron" in result["message"].lower()

    @patch("services.github_client._estimate_active_days", return_value=0)
    @patch("services.github_client.requests.get")
    def test_contributor_sin_campos_opcionales(self, mock_get, mock_days):
        # Algunos contributors pueden no traer avatar_url o contributions
        mock_get.return_value = _mock_response(200, [
            {"login": "solo-login"},  # sin avatar_url ni contributions
        ])

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert len(result["contributors"]) == 1
        assert result["contributors"][0]["username"] == "solo-login"
        assert result["contributors"][0]["commits"] == 0
        assert result["contributors"][0]["avatar_url"] == ""

    @patch("services.github_client.requests.get")
    def test_error_de_conexion(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        with pytest.raises(Exception) as exc:
            get_contributors_from_api("https://github.com/owner/repo")
        assert "conexión" in str(exc.value).lower() or "connection" in str(exc.value).lower()

    @patch("services.github_client.requests.get")
    def test_error_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Timed out")

        with pytest.raises(Exception) as exc:
            get_contributors_from_api("https://github.com/owner/repo")
        assert "conexión" in str(exc.value).lower() or "connection" in str(exc.value).lower()

    @patch("services.github_client.requests.get")
    def test_url_invalida_lanza_excepcion(self, mock_get):
        with pytest.raises(Exception) as exc:
            get_contributors_from_api("https://gitlab.com/owner/repo")
        # ValueError es capturado por el except general
        assert "error" in str(exc.value).lower()

    @patch("services.github_client._estimate_active_days", return_value=15)
    @patch("services.github_client.requests.get")
    def test_estructura_completa_de_retorno(self, mock_get, mock_days):
        mock_get.return_value = _mock_response(200, [
            {"login": "alice", "avatar_url": "https://x.com/a.png", "contributions": 10},
        ])

        result = get_contributors_from_api("https://github.com/owner/repo")

        claves_esperadas = [
            "contributors", "total_commits", "unique_authors",
            "active_days", "repo_url", "repo_name",
        ]
        for k in claves_esperadas:
            assert k in result, f"Falta clave: {k}"

        # Verificar estructura de cada contributor
        c = result["contributors"][0]
        for k in ["username", "name", "email", "avatar_url", "commits", "role"]:
            assert k in c, f"Falta clave en contributor: {k}"

    @patch("services.github_client._estimate_active_days", return_value=0)
    @patch("services.github_client.requests.get")
    def test_usa_headers_correctos(self, mock_get, mock_days):
        mock_get.return_value = _mock_response(200, [])

        get_contributors_from_api("https://github.com/owner/repo")

        # Verificar que se pasó el header Accept correcto
        call_kwargs = mock_get.call_args.kwargs
        assert "headers" in call_kwargs
        assert "Accept" in call_kwargs["headers"]
        assert "github" in call_kwargs["headers"]["Accept"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _estimate_active_days
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimateActiveDays:
    @patch("services.github_client.requests.get")
    def test_cuenta_dias_unicos(self, mock_get):
        mock_get.return_value = _mock_response(200, [
            {"commit": {"author": {"date": "2024-01-15T10:00:00Z"}}},
            {"commit": {"author": {"date": "2024-01-15T15:00:00Z"}}},  # mismo día
            {"commit": {"author": {"date": "2024-01-16T09:00:00Z"}}},  # día distinto
            {"commit": {"author": {"date": "2024-01-17T12:00:00Z"}}},  # día distinto
        ])

        result = _estimate_active_days("owner", "repo")
        assert result == 3  # 3 días únicos

    @patch("services.github_client.requests.get")
    def test_respuesta_vacia_devuelve_cero(self, mock_get):
        mock_get.return_value = _mock_response(200, [])
        assert _estimate_active_days("owner", "repo") == 0

    @patch("services.github_client.requests.get")
    def test_status_no_200_devuelve_cero(self, mock_get):
        mock_get.return_value = _mock_response(500, [])
        assert _estimate_active_days("owner", "repo") == 0

    @patch("services.github_client.requests.get")
    def test_status_404_devuelve_cero(self, mock_get):
        mock_get.return_value = _mock_response(404, [])
        assert _estimate_active_days("owner", "repo") == 0

    @patch("services.github_client.requests.get")
    def test_excepcion_devuelve_cero(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        assert _estimate_active_days("owner", "repo") == 0

    @patch("services.github_client.requests.get")
    def test_commits_sin_fecha_se_ignoran(self, mock_get):
        mock_get.return_value = _mock_response(200, [
            {"commit": {"author": {"date": "2024-01-15T10:00:00Z"}}},
            {"commit": {"author": {}}},  # sin date
            {"commit": {}},               # sin author
            {},                            # commit vacío
        ])

        result = _estimate_active_days("owner", "repo")
        assert result == 1

    @patch("services.github_client.requests.get")
    def test_usa_parametro_per_page(self, mock_get):
        mock_get.return_value = _mock_response(200, [])
        _estimate_active_days("owner", "repo")

        call_kwargs = mock_get.call_args.kwargs
        assert "params" in call_kwargs
        assert call_kwargs["params"]["per_page"] == 100

    @patch("services.github_client.requests.get")
    def test_url_correcta(self, mock_get):
        mock_get.return_value = _mock_response(200, [])
        _estimate_active_days("octocat", "Hello-World")

        call_args = mock_get.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "octocat" in url
        assert "Hello-World" in url
        assert "commits" in url


# ─────────────────────────────────────────────────────────────────────────────
# Tests de integración
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    @patch("services.github_client._estimate_active_days", return_value=42)
    @patch("services.github_client.requests.get")
    def test_flujo_completo_contributors(self, mock_get, mock_days):
        mock_get.return_value = _mock_response(200, [
            {"login": "alice", "avatar_url": "https://x.com/a.png", "contributions": 200},
            {"login": "bob", "avatar_url": "https://x.com/b.png", "contributions": 100},
        ])

        result = get_contributors_from_api("https://github.com/owner/repo")

        assert result["unique_authors"] == 2
        assert result["total_commits"] == 300
        assert result["active_days"] == 42
        assert result["contributors"][0]["username"] == "alice"
        assert result["contributors"][0]["role"] == "contributor"
        assert result["repo_url"] == "https://github.com/owner/repo"

    @patch("services.github_client.requests.get")
    def test_flujo_con_url_en_distintos_formatos(self, mock_get):
        mock_get.return_value = _mock_response(404, {})

        urls = [
            "https://github.com/owner/repo",
            "github.com/owner/repo",
            "https://github.com/owner/repo.git",
            "  https://github.com/owner/repo  ",
        ]
        for url in urls:
            result = get_contributors_from_api(url)
            assert result["contributors"] == []