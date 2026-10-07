"""
tests/test_ai_enhancer.py

Tests unitarios para services/ai_enhancer.py
Ejecutar con: python -m pytest tests/test_ai_enhancer.py -v
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock, mock_open

# Aseguramos que el módulo se importe con sys.path correcto (lo hace conftest.py)
from services.ai_enhancer import AIEnhancer


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def enhancer_without_keys(monkeypatch):
    """Instancia de AIEnhancer SIN API keys configuradas."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return AIEnhancer()


@pytest.fixture
def enhancer_with_keys(monkeypatch):
    """Instancia de AIEnhancer CON una API key configurada."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-12345")
    return AIEnhancer()


@pytest.fixture
def enhancer_with_multiple_keys(monkeypatch):
    """Instancia con múltiples API keys separadas por coma."""
    monkeypatch.setenv("GROQ_API_KEY", "key1, key2, key3")
    return AIEnhancer()


@pytest.fixture
def sample_function():
    """Función de ejemplo."""
    return {
        "name": "calculate_total",
        "params": ["price", "quantity"],
        "file": "billing.py",
        "docstring": "Calcula el total",
        "complexity": 3,
    }


@pytest.fixture
def sample_class():
    """Clase de ejemplo."""
    return {
        "name": "UserService",
        "methods": ["get_user", "create_user", "delete_user"],
        "bases": ["BaseService"],
        "file": "user_service.py",
        "docstring": "Servicio de usuarios",
    }


@pytest.fixture
def sample_endpoint():
    """Endpoint de ejemplo."""
    return {
        "method": "GET",
        "path": "/api/users",
        "framework": "Flask",
        "file": "routes.py",
    }


@pytest.fixture
def sample_analysis_results():
    """Resultados de análisis de ejemplo."""
    return {
        "primary_language": "Python",
        "languages": {"Python": 1000, "JavaScript": 200},
        "functions": [
            {"name": "get_user", "complexity": 3, "docstring": "doc"},
            {"name": "create_user", "complexity": 7, "docstring": ""},
            {"name": "delete_user", "complexity": 12, "docstring": "doc"},
        ],
        "classes": [
            {"name": "UserController"},
            {"name": "UserService"},
        ],
        "endpoints": [
            {"method": "GET", "path": "/users"},
            {"method": "POST", "path": "/users"},
        ],
        "structure": [
            {"path": "controllers/user.py"},
            {"path": "services/user.py"},
            {"path": "models/user.py"},
        ],
    }


def _mock_groq_response(content: str, status_code: int = 200):
    """Helper que crea un mock de respuesta HTTP de Groq."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    mock_resp.text = content
    return mock_resp


# ─────────────────────────────────────────────────────────────────────────────
# Tests: __init__ / configuración
# ─────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_sin_api_key(self, enhancer_without_keys):
        assert enhancer_without_keys.api_keys == []
        assert enhancer_without_keys.is_available() is False

    def test_con_una_api_key(self, enhancer_with_keys):
        assert enhancer_with_keys.api_keys == ["test-key-12345"]
        assert enhancer_with_keys.is_available() is True

    def test_con_multiples_api_keys(self, enhancer_with_multiple_keys):
        assert enhancer_with_multiple_keys.api_keys == ["key1", "key2", "key3"]
        assert enhancer_with_multiple_keys.is_available() is True

    def test_api_keys_con_espacios(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "  key1  ,  key2  ,  , key3")
        enhancer = AIEnhancer()
        assert enhancer.api_keys == ["key1", "key2", "key3"]

    def test_api_url_configurada(self, enhancer_with_keys):
        assert enhancer_with_keys.API_URL == "https://api.groq.com/openai/v1/chat/completions"

    def test_current_key_index_inicia_en_cero(self, enhancer_with_keys):
        assert enhancer_with_keys.current_key_index == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: get_api_key (rotación)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetApiKey:
    def test_sin_keys_devuelve_none(self, enhancer_without_keys):
        assert enhancer_without_keys.get_api_key() is None

    def test_una_key_siempre_devuelve_la_misma(self, enhancer_with_keys):
        assert enhancer_with_keys.get_api_key() == "test-key-12345"
        assert enhancer_with_keys.get_api_key() == "test-key-12345"
        assert enhancer_with_keys.get_api_key() == "test-key-12345"

    def test_rotacion_circular(self, enhancer_with_multiple_keys):
        assert enhancer_with_multiple_keys.get_api_key() == "key1"
        assert enhancer_with_multiple_keys.get_api_key() == "key2"
        assert enhancer_with_multiple_keys.get_api_key() == "key3"
        # Vuelve a empezar
        assert enhancer_with_multiple_keys.get_api_key() == "key1"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: is_available
# ─────────────────────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_sin_keys(self, enhancer_without_keys):
        assert enhancer_without_keys.is_available() is False

    def test_con_keys(self, enhancer_with_keys):
        assert enhancer_with_keys.is_available() is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _call_ai
# ─────────────────────────────────────────────────────────────────────────────

class TestCallAI:
    @patch("services.ai_enhancer.requests.post")
    def test_llamada_exitosa(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response("Respuesta de prueba")
        result = enhancer_with_keys._call_ai("system", "user")
        assert result == "Respuesta de prueba"
        assert mock_post.called

    def test_sin_api_keys_devuelve_none(self, enhancer_without_keys):
        result = enhancer_without_keys._call_ai("system", "user")
        assert result is None

    @patch("services.ai_enhancer.requests.post")
    def test_error_401_rota_a_siguiente_key(self, mock_post, enhancer_with_multiple_keys):
        # key1 falla con 401, key2 funciona
        resp_fail = _mock_groq_response("Unauthorized", status_code=401)
        resp_ok = _mock_groq_response("OK con key2", status_code=200)
        mock_post.side_effect = [resp_fail, resp_ok]

        result = enhancer_with_multiple_keys._call_ai("sys", "usr")
        assert result == "OK con key2"
        assert mock_post.call_count == 2

    @patch("services.ai_enhancer.requests.post")
    def test_error_403_rota_a_siguiente_key(self, mock_post, enhancer_with_multiple_keys):
        resp_fail = _mock_groq_response("Forbidden", status_code=403)
        resp_ok = _mock_groq_response("OK", status_code=200)
        mock_post.side_effect = [resp_fail, resp_ok]
        result = enhancer_with_multiple_keys._call_ai("sys", "usr")
        assert result == "OK"

    @patch("services.ai_enhancer.requests.post")
    def test_error_500_devuelve_none(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response("Server Error", status_code=500)
        result = enhancer_with_keys._call_ai("sys", "usr")
        assert result is None

    @patch("services.ai_enhancer.requests.post")
    def test_excepcion_de_conexion_rota_key(self, mock_post, enhancer_with_multiple_keys):
        resp_ok = _mock_groq_response("OK con key2", status_code=200)
        # Primera llamada lanza excepción, segunda devuelve OK
        mock_post.side_effect = [Exception("Timeout"), resp_ok]
        result = enhancer_with_multiple_keys._call_ai("sys", "usr")
        assert result == "OK con key2"

    @patch("services.ai_enhancer.requests.post")
    def test_todas_las_keys_fallan(self, mock_post, enhancer_with_multiple_keys):
        mock_post.side_effect = Exception("Network error")
        result = enhancer_with_multiple_keys._call_ai("sys", "usr")
        assert result is None
        assert mock_post.call_count == 3  # 3 keys intentadas

    @patch("services.ai_enhancer.requests.post")
    def test_respuesta_vacia_devuelve_none(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response("")
        result = enhancer_with_keys._call_ai("sys", "usr")
        # Como no hay contenido, retorna None tras intentar todas las keys
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_function_description
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceFunctionDescription:
    def test_sin_ia_usa_docstring_existente(self, enhancer_without_keys, sample_function):
        result = enhancer_without_keys.enhance_function_description(sample_function)
        assert result == "Calcula el total"

    def test_sin_ia_sin_docstring_devuelve_nombre(self, enhancer_without_keys, sample_function):
        sample_function["docstring"] = ""
        result = enhancer_without_keys.enhance_function_description(sample_function)
        assert "calculate_total" in result

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_devuelve_respuesta(self, mock_post, enhancer_with_keys, sample_function):
        mock_post.return_value = _mock_groq_response("Descripción mejorada por IA")
        result = enhancer_with_keys.enhance_function_description(sample_function)
        assert result == "Descripción mejorada por IA"

    @patch("services.ai_enhancer.requests.post")
    def test_ia_falla_devuelve_docstring(self, mock_post, enhancer_with_keys, sample_function):
        mock_post.side_effect = Exception("API caída")
        result = enhancer_with_keys.enhance_function_description(sample_function)
        assert result == "Calcula el total"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_class_description
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceClassDescription:
    def test_sin_ia_usa_docstring(self, enhancer_without_keys, sample_class):
        result = enhancer_without_keys.enhance_class_description(sample_class)
        assert result == "Servicio de usuarios"

    def test_sin_ia_sin_docstring(self, enhancer_without_keys, sample_class):
        sample_class["docstring"] = ""
        result = enhancer_without_keys.enhance_class_description(sample_class)
        assert "UserService" in result

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia(self, mock_post, enhancer_with_keys, sample_class):
        mock_post.return_value = _mock_groq_response("Clase mejorada")
        result = enhancer_with_keys.enhance_class_description(sample_class)
        assert result == "Clase mejorada"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_endpoint_description
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceEndpointDescription:
    def test_sin_ia_devuelve_string_basico(self, enhancer_without_keys, sample_endpoint):
        result = enhancer_without_keys.enhance_endpoint_description(sample_endpoint)
        assert "GET" in result
        assert "/api/users" in result

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia(self, mock_post, enhancer_with_keys, sample_endpoint):
        mock_post.return_value = _mock_groq_response("Endpoint mejorado")
        result = enhancer_with_keys.enhance_endpoint_description(sample_endpoint)
        assert result == "Endpoint mejorado"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_architecture_insights
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateArchitectureInsights:
    def test_sin_ia_devuelve_mensaje(self, enhancer_without_keys, sample_analysis_results):
        result = enhancer_without_keys.generate_architecture_insights(sample_analysis_results)
        assert "no disponibles" in result.lower() or "configura" in result.lower()

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia(self, mock_post, enhancer_with_keys, sample_analysis_results):
        mock_post.return_value = _mock_groq_response("Insights de arquitectura")
        result = enhancer_with_keys.generate_architecture_insights(sample_analysis_results)
        assert result == "Insights de arquitectura"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_documentation
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceDocumentation:
    def test_sin_ia_devuelve_resultados_intactos(self, enhancer_without_keys, sample_analysis_results):
        result = enhancer_without_keys.enhance_documentation(sample_analysis_results)
        assert result is sample_analysis_results  # mismo objeto
        # No debe añadir claves ai_description
        for f in result["functions"]:
            assert "ai_description" not in f

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_agrega_descripciones(self, mock_post, enhancer_with_keys, sample_analysis_results):
        mock_post.return_value = _mock_groq_response("Mejorado por IA")
        result = enhancer_with_keys.enhance_documentation(sample_analysis_results)

        # Debe agregar ai_description a funciones (máx 5), clases (máx 3), endpoints (máx 3)
        for f in result["functions"][:5]:
            assert "ai_description" in f
            assert f["ai_description"] == "Mejorado por IA"

        for c in result["classes"][:3]:
            assert "ai_description" in c

        for e in result["endpoints"][:3]:
            assert "ai_description" in e

        # Debe agregar insights de arquitectura
        assert "ai_architecture_insights" in result

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_limita_cantidad_llamadas(self, mock_post, enhancer_with_keys, sample_analysis_results):
        mock_post.return_value = _mock_groq_response("OK")
        enhancer_with_keys.enhance_documentation(sample_analysis_results)
        # 3 funciones (menos de 5) + 2 clases (menos de 3) + 2 endpoints (menos de 3) + 1 arquitectura = 8
        assert mock_post.call_count == 8


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_database_analysis
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceDatabaseAnalysis:
    def test_sin_ia(self, enhancer_without_keys):
        result = enhancer_without_keys.enhance_database_analysis("CREATE TABLE...", {"tables": []})
        assert "no disponible" in result.lower()

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response("Informe SQL")
        metadata = {
            "tables": ["users", "orders"],
            "data_sources": {
                "structured": ["users"],
                "semi_structured": ["logs"],
                "unstructured": ["docs"],
            },
            "warehouse_schema": {
                "type": "star",
                "description": "Esquema estrella",
            },
        }
        result = enhancer_with_keys.enhance_database_analysis("CREATE TABLE users();", metadata)
        assert result == "Informe SQL"

    @patch("services.ai_enhancer.requests.post")
    def test_ia_falla(self, mock_post, enhancer_with_keys):
        mock_post.side_effect = Exception("Error")
        metadata = {
            "tables": [],
            "data_sources": {"structured": [], "semi_structured": [], "unstructured": []},
            "warehouse_schema": {"type": "unknown", "description": ""},
        }
        result = enhancer_with_keys.enhance_database_analysis("SQL", metadata)
        assert "no disponible" in result.lower() or "no se recibió" in result.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: enhance_database_report_sections
# ─────────────────────────────────────────────────────────────────────────────

class TestEnhanceDatabaseReportSections:
    def test_sin_ia_devuelve_dict_vacio(self, enhancer_without_keys):
        result = enhancer_without_keys.enhance_database_report_sections({"summary": "x"})
        assert result == {}

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_json_valido(self, mock_post, enhancer_with_keys):
        payload = {
            "summary": "Resumen mejorado",
            "data_preparation": ["item 1", "item 2"],
            "data_mining_insights": ["insight 1"],
            "suggestions": ["sugerencia 1"],
            "warehouse_description": "Descripción mejorada",
        }
        mock_post.return_value = _mock_groq_response(json.dumps(payload))

        result = enhancer_with_keys.enhance_database_report_sections({"summary": "viejo"})
        assert result["summary"] == "Resumen mejorado"
        assert result["data_preparation"] == ["item 1", "item 2"]

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_json_con_markdown(self, mock_post, enhancer_with_keys):
        payload = {"summary": "OK", "data_preparation": [], "data_mining_insights": [], "suggestions": [], "warehouse_description": ""}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        mock_post.return_value = _mock_groq_response(wrapped)

        result = enhancer_with_keys.enhance_database_report_sections({"summary": "x"})
        assert result["summary"] == "OK"

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_json_invalido(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response("esto no es JSON")
        result = enhancer_with_keys.enhance_database_report_sections({"summary": "x"})
        assert result == {}

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_json_no_dict(self, mock_post, enhancer_with_keys):
        mock_post.return_value = _mock_groq_response('["lista", "no", "dict"]')
        result = enhancer_with_keys.enhance_database_report_sections({"summary": "x"})
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: mine_code_patterns
# ─────────────────────────────────────────────────────────────────────────────

class TestMineCodePatterns:
    def test_sin_ia_devuelve_fallback(self, enhancer_without_keys, sample_analysis_results):
        result = enhancer_without_keys.mine_code_patterns(sample_analysis_results)
        assert "frequent_patterns" in result
        assert "complexity_clusters" in result
        assert "function_clusters" in result
        assert "insights" in result
        assert "no disponible" in result["insights"].lower()

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_json_valido(self, mock_post, enhancer_with_keys, sample_analysis_results):
        payload = {
            "frequent_patterns": [{"pattern": "get_", "frequency": 3, "examples": ["get_user"]}],
            "complexity_clusters": [{"cluster": "baja", "count": 10, "avg_complexity": 2}],
            "function_clusters": [{"cluster": "controllers", "files": ["a.py"], "functions": ["f1"]}],
            "anomalies": [],
        }
        mock_post.return_value = _mock_groq_response(json.dumps(payload))

        result = enhancer_with_keys.mine_code_patterns(sample_analysis_results)
        assert result["frequent_patterns"][0]["pattern"] == "get_"
        assert "insights" in result

    @patch("services.ai_enhancer.requests.post")
    def test_con_ia_respuesta_invalida_usa_fallback(self, mock_post, enhancer_with_keys, sample_analysis_results):
        mock_post.return_value = _mock_groq_response("no es json")
        result = enhancer_with_keys.mine_code_patterns(sample_analysis_results)
        # Debe haber caído en _mine_patterns_simple
        assert "insights" in result
        assert "simple" in result["insights"].lower() or "no disponible" in result["insights"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _mine_patterns_simple (fallback)
# ─────────────────────────────────────────────────────────────────────────────

class TestMinePatternsSimple:
    def test_detecta_prefijos_frecuentes(self, enhancer_without_keys):
        results = {
            "functions": [
                {"name": "get_user", "complexity": 2},
                {"name": "get_order", "complexity": 3},
                {"name": "get_product", "complexity": 1},
                {"name": "create_user", "complexity": 5},
                {"name": "update_user", "complexity": 4},
            ],
            "classes": [],
            "structure": [],
        }
        result = enhancer_without_keys._mine_patterns_simple(results)
        patterns = {p["pattern"] for p in result["frequent_patterns"]}
        assert "get_" in patterns

    def test_clustering_por_complejidad(self, enhancer_without_keys):
        results = {
            "functions": [
                {"name": "f1", "complexity": 2},   # baja
                {"name": "f2", "complexity": 3},   # baja
                {"name": "f3", "complexity": 7},   # media
                {"name": "f4", "complexity": 15},  # alta
            ],
            "classes": [],
            "structure": [],
        }
        result = enhancer_without_keys._mine_patterns_simple(results)
        clusters = {c["cluster"]: c["count"] for c in result["complexity_clusters"]}
        assert clusters["baja"] == 2
        assert clusters["media"] == 1
        assert clusters["alta"] == 1

    def test_clustering_por_directorio(self, enhancer_without_keys):
        results = {
            "functions": [],
            "classes": [],
            "structure": [
                {"path": "controllers/user.py"},
                {"path": "controllers/order.py"},
                {"path": "services/user.py"},
            ],
        }
        result = enhancer_without_keys._mine_patterns_simple(results)
        clusters = {c["cluster"] for c in result["function_clusters"]}
        assert "controllers" in clusters
        assert "services" in clusters

    def test_resultado_tiene_todas_las_claves(self, enhancer_without_keys):
        result = enhancer_without_keys._mine_patterns_simple({"functions": [], "classes": [], "structure": []})
        for k in ["frequent_patterns", "complexity_clusters", "function_clusters", "anomalies", "insights"]:
            assert k in result