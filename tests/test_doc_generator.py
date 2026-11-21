"""
tests/test_doc_generator.py

Tests unitarios para services/doc_generator.py
Ejecutar con: python -m pytest tests/test_doc_generator.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from services.doc_generator import DocGenerator
from services.ai_enhancer import AIEnhancer


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_ai_enhancer():
    """
    Mock global de AIEnhancer para TODOS los tests.
    Evita llamadas reales a Groq y mantiene el output determinista.
    """
    with patch("services.doc_generator.AIEnhancer") as MockAI:
        instance = MagicMock()
        instance.is_available.return_value = False  # Sin IA por defecto
        MockAI.return_value = instance
        yield MockAI


@pytest.fixture(autouse=True)
def mock_plantuml():
    """
    Mock global de _generate_plantuml_diagram para que no intente ejecutar
    Java ni descargar imágenes. Devuelve una URI vacía por defecto.
    """
    with patch.object(DocGenerator, "_generate_plantuml_diagram", return_value="") as mock:
        yield mock


@pytest.fixture
def minimal_results():
    """Análisis mínimo (sin funciones, clases, endpoints)."""
    return {
        "primary_language": "Python",
        "languages": {"Python": 5},
        "total_files": 5,
        "functions": [],
        "classes": [],
        "endpoints": [],
        "structure": [],
        "issues": [],
        "complexity": {"avg": 1.0, "max": 1, "high_complexity_funcs": 0},
        "quality_score": 75,
    }


@pytest.fixture
def full_results():
    """Análisis completo con datos representativos."""
    return {
        "primary_language": "Python",
        "languages": {"Python": 10, "JavaScript": 3},
        "total_files": 13,
        "functions": [
            {
                "name": "get_user",
                "file": "services/user.py",
                "line": 10,
                "params": ["user_id"],
                "docstring": "Obtiene un usuario por ID",
                "is_async": False,
                "complexity": 2,
            },
            {
                "name": "create_user",
                "file": "services/user.py",
                "line": 20,
                "params": ["data"],
                "docstring": "",
                "is_async": True,
                "complexity": 8,
            },
            {
                "name": "delete_user",
                "file": "services/user.py",
                "line": 30,
                "params": ["user_id"],
                "docstring": "Elimina usuario",
                "is_async": False,
                "complexity": 15,
            },
            {
                "name": "test_login",
                "file": "tests/test_auth.py",
                "line": 5,
                "params": [],
                "docstring": "Test de login",
                "is_async": False,
                "complexity": 1,
            },
        ],
        "classes": [
            {
                "name": "UserModel",
                "file": "models/user.py",
                "line": 1,
                "bases": ["BaseModel"],
                "methods": ["save", "delete", "to_dict"],
                "docstring": "Modelo de usuario",
            },
            {
                "name": "bad_name",
                "file": "models/bad.py",
                "line": 5,
                "bases": [],
                "methods": [],
                "docstring": "",
            },
        ],
        "endpoints": [
            {
                "method": "GET",
                "path": "/api/users",
                "file": "routes/users.py",
                "framework": "Flask",
            },
            {
                "method": "POST",
                "path": "/api/users",
                "file": "routes/users.py",
                "framework": "Flask",
            },
        ],
        "structure": [
            {"path": "services/user.py", "name": "user.py"},
            {"path": "routes/users.py", "name": "users.py"},
            {"path": "models/user.py", "name": "user.py"},
        ],
        "issues": [{"file": "bad.py", "error": "Syntax error"}],
        "complexity": {"avg": 4.5, "max": 15, "high_complexity_funcs": 1},
        "quality_score": 65,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests: __init__
# ─────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_guarda_analysis_results(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert gen.r is not None
        assert gen.r["primary_language"] == "Python"

    def test_genera_timestamp(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert "UTC" in gen.now

    def test_sin_ia_no_modifica_resultados(self, minimal_results):
        original_keys = set(minimal_results.keys())
        gen = DocGenerator(minimal_results)
        assert set(gen.r.keys()) == original_keys

    def test_con_ia_disponible_llama_enhance(self, minimal_results, monkeypatch):
        monkeypatch.setenv("ENABLE_AI_ANALYSIS", "true")
        with patch("services.doc_generator.AIEnhancer") as MockAI:
            instance = MagicMock()
            instance.is_available.return_value = True
            instance.enhance_documentation.return_value = {**minimal_results, "ai_added": True}
            MockAI.return_value = instance

            gen = DocGenerator(minimal_results)
            instance.enhance_documentation.assert_called_once()
            assert gen.r.get("ai_added") is True

    def test_activa_ia_con_clave_sin_bandera_explicita(self, minimal_results, monkeypatch):
        monkeypatch.delenv("ENABLE_AI_ANALYSIS", raising=False)
        with patch("services.doc_generator.AIEnhancer") as MockAI:
            instance = MagicMock()
            instance.is_available.return_value = True
            instance.enhance_documentation.return_value = {**minimal_results, "ai_added": True}
            MockAI.return_value = instance

            gen = DocGenerator(minimal_results)

            instance.enhance_documentation.assert_called_once()
            assert gen.r.get("ai_added") is True

    def test_no_repite_enriquecimiento_ya_hecho_en_el_mismo_idioma(self, minimal_results, monkeypatch):
        monkeypatch.setenv("ENABLE_AI_ANALYSIS", "true")
        minimal_results.update({
            "ai_documentation_enhanced": True,
            "ai_output_language": "es",
            "ai_documentation_version": AIEnhancer.DOCUMENTATION_VERSION,
        })
        gen = DocGenerator(minimal_results, lang="es")
        gen.ai_enhancer.enhance_documentation.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _render_markdown_table
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderMarkdownTable:
    def test_tabla_simple(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen._render_markdown_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert "| A | B |" in result
        assert "| --- | --- |" in result
        assert "| 1 | 2 |" in result
        assert "| 3 | 4 |" in result

    def test_tabla_vacia(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen._render_markdown_table(["A"], [])
        assert "| A |" in result
        assert "| --- |" in result

    def test_tabla_multiples_columnas(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen._render_markdown_table(["X", "Y", "Z"], [["a", "b", "c"]])
        assert "| X | Y | Z |" in result
        assert "| a | b | c |" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _graphviz_available
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphvizAvailable:
    def test_true_cuando_dot_existe(self, minimal_results):
        gen = DocGenerator(minimal_results)
        with patch("services.doc_generator.shutil.which", return_value="/usr/bin/dot"):
            assert gen._graphviz_available() is True

    def test_false_cuando_dot_no_existe(self, minimal_results):
        gen = DocGenerator(minimal_results)
        with patch("services.doc_generator.shutil.which", return_value=None):
            assert gen._graphviz_available() is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _encode6 y _plantuml_encode
# ─────────────────────────────────────────────────────────────────────────────

class TestPlantumlEncode:
    def test_encode6_valor_cero(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert gen._encode6(0) == "0"

    def test_encode6_valor_maximo(self, minimal_results):
        gen = DocGenerator(minimal_results)
        # 0x3F = 63 → último carácter del alfabeto
        assert gen._encode6(63) == "_"

    def test_encode6_valores_en_rango(self, minimal_results):
        gen = DocGenerator(minimal_results)
        for v in [0, 1, 10, 32, 63]:
            result = gen._encode6(v)
            assert len(result) == 1
            assert result in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"

    def test_plantuml_encode_devuelve_string(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen._plantuml_encode("@startuml\nA -> B\n@enduml")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_plantuml_encode_es_determinista(self, minimal_results):
        gen = DocGenerator(minimal_results)
        text = "@startuml\nclass A\n@enduml"
        r1 = gen._plantuml_encode(text)
        r2 = gen._plantuml_encode(text)
        assert r1 == r2

    def test_plantuml_encode_textos_distintos(self, minimal_results):
        gen = DocGenerator(minimal_results)
        r1 = gen._plantuml_encode("texto A")
        r2 = gen._plantuml_encode("texto B")
        assert r1 != r2


class TestPlantTextServer:
    def test_intenta_planttext_primero(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        response = MagicMock()
        response.status = 200
        response.read.return_value = b"\x89PNG\r\n\x1a\n" + b"x" * 500
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch("services.doc_generator.urllib.request.urlopen", return_value=response) as urlopen, \
             patch.object(gen, "_is_valid_image", return_value=True):
            output = gen._fetch_plantuml_image("@startuml\nA -> B\n@enduml", tmp_path / "diagram")

        assert output == tmp_path / "diagram.png"
        assert "https://www.planttext.com/plantuml/png/" in urlopen.call_args.args[0].full_url


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _is_valid_image
# ─────────────────────────────────────────────────────────────────────────────

class TestIsValidImage:
    def test_png_invalido_muy_pequeno(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "small.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"a" * 50)  # muy pequeño
        assert gen._is_valid_image(png) is False

    def test_png_valido(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "valid.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 500)
        assert gen._is_valid_image(png) is True

    def test_png_con_error_de_plantuml(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "error.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"cannot find graphviz" + b"x" * 500)
        assert gen._is_valid_image(png) is False

    def test_svg_valido(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        svg = tmp_path / "valid.svg"
        svg.write_text("<svg></svg>", encoding="utf-8")
        assert gen._is_valid_image(svg) is True

    def test_svg_invalido(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        svg = tmp_path / "invalid.svg"
        svg.write_text("no es svg", encoding="utf-8")
        assert gen._is_valid_image(svg) is False

    def test_archivo_inexistente(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "no_existe.png"
        assert gen._is_valid_image(png) is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _contains_plantuml_error_text
# ─────────────────────────────────────────────────────────────────────────────

class TestContainsPlantumlErrorText:
    def test_detecta_graphviz(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert gen._contains_plantuml_error_text(b"cannot find graphviz") is True

    def test_detecta_dot_executable(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert gen._contains_plantuml_error_text(b"dot executable does not exist") is True

    def test_no_detecta_texto_normal(self, minimal_results):
        gen = DocGenerator(minimal_results)
        assert gen._contains_plantuml_error_text(b"esto es un PNG normal") is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _image_to_data_uri
# ─────────────────────────────────────────────────────────────────────────────

class TestImageToDataUri:
    def test_png_valido_devuelve_data_uri(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "valid.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 500)
        result = gen._image_to_data_uri(png)
        assert result.startswith("data:image/png;base64,")

    def test_png_invalido_devuelve_vacio(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        png = tmp_path / "invalid.png"
        png.write_bytes(b"no es png")
        result = gen._image_to_data_uri(png)
        assert result == ""

    def test_archivo_inexistente(self, minimal_results, tmp_path):
        gen = DocGenerator(minimal_results)
        result = gen._image_to_data_uri(tmp_path / "no.png")
        assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate (estructura de salida)
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerate:
    def test_devuelve_todas_las_claves(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen.generate()
        claves = [
            "generated_at", "readme", "architecture", "api_docs",
            "class_docs", "function_docs", "data_models", "deployment",
            "quality_report", "full_markdown",
        ]
        for k in claves:
            assert k in result, f"Falta clave: {k}"

    def test_tipos_de_datos(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen.generate()
        assert isinstance(result["api_docs"], list)
        assert isinstance(result["class_docs"], list)
        assert isinstance(result["function_docs"], list)
        assert isinstance(result["readme"], str)
        assert isinstance(result["architecture"], str)

    def test_reutiliza_diagramas_al_ensamblar_markdown(self, minimal_results):
        gen = DocGenerator(minimal_results)
        with patch.object(gen, "_architecture", wraps=gen._architecture) as architecture:
            with patch.object(gen, "_data_models", wraps=gen._data_models) as data_models:
                gen.generate()

        assert architecture.call_count == 1
        assert data_models.call_count == 1

    def test_full_markdown_no_vacio(self, full_results):
        gen = DocGenerator(full_results)
        result = gen.generate()
        assert len(result["full_markdown"]) > 1000
        assert "Documentación del Proyecto" in result["full_markdown"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _readme
# ─────────────────────────────────────────────────────────────────────────────

class TestReadme:
    def test_incluye_lenguaje_y_score(self, full_results):
        gen = DocGenerator(full_results)
        readme = gen._readme()
        assert "Python" in readme
        assert "65/100" in readme

    def test_incluye_conteos(self, full_results):
        gen = DocGenerator(full_results)
        readme = gen._readme()
        assert "4" in readme  # 4 funciones
        assert "2" in readme  # 2 clases

    def test_datos_vacios_no_falla(self, minimal_results):
        gen = DocGenerator(minimal_results)
        readme = gen._readme()
        assert "Python" in readme


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _architecture
# ─────────────────────────────────────────────────────────────────────────────

class TestArchitecture:
    def test_incluye_estructura(self, full_results):
        gen = DocGenerator(full_results)
        arch = gen._architecture()
        assert "services/" in arch or "routes/" in arch

    def test_incluye_secciones(self, full_results):
        gen = DocGenerator(full_results)
        arch = gen._architecture()
        assert "2.1" in arch
        assert "2.2" in arch
        assert "2.3" in arch

    def test_sin_estructura_no_falla(self, minimal_results):
        gen = DocGenerator(minimal_results)
        arch = gen._architecture()
        assert isinstance(arch, str)

    def test_incluye_lineas_por_archivo_y_total(self, minimal_results):
        minimal_results["structure"] = [
            {"path": "src/main.py", "name": "main.py", "line_count": 12},
            {"path": "src/utils.py", "name": "utils.py", "line_count": 8},
        ]
        arch = DocGenerator(minimal_results)._architecture()

        assert "| `src/main.py` | 12 |" in arch
        assert "| `src/utils.py` | 8 |" in arch
        assert "Total de líneas de archivos contadas:** 20 (2/2 archivos)" in arch

    def test_menciona_insights_ia_si_no_hay(self, minimal_results):
        gen = DocGenerator(minimal_results)
        arch = gen._architecture()
        # No debe contener texto de IA porque no está configurada
        assert "Insights de Arquitectura" in arch


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _detect_patterns
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectPatterns:
    def test_detecta_api_rest(self, full_results):
        gen = DocGenerator(full_results)
        patterns = gen._detect_patterns()
        assert "API REST" in patterns
        assert "2 endpoints" in patterns

    def test_detecta_mvc(self, full_results):
        gen = DocGenerator(full_results)
        patterns = gen._detect_patterns()
        assert "MVC" in patterns or "Model" in patterns

    def test_detecta_tests(self, full_results):
        gen = DocGenerator(full_results)
        patterns = gen._detect_patterns()
        assert "Testing" in patterns or "prueba" in patterns

    def test_detecta_async(self, full_results):
        gen = DocGenerator(full_results)
        patterns = gen._detect_patterns()
        assert "Asíncrona" in patterns or "async" in patterns.lower()

    def test_sin_patrones(self, minimal_results):
        gen = DocGenerator(minimal_results)
        patterns = gen._detect_patterns()
        assert "No se detectaron" in patterns


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _api_docs
# ─────────────────────────────────────────────────────────────────────────────

class TestApiDocs:
    def test_devuelve_lista(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._api_docs()
        assert isinstance(docs, list)
        assert len(docs) == 2

    def test_estructura_de_cada_doc(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._api_docs()
        for d in docs:
            assert "method" in d
            assert "path" in d
            assert "file" in d
            assert "responses" in d
            assert "200" in d["responses"]

    def test_usa_descripcion_ia_si_existe(self, full_results):
        full_results["endpoints"][0]["ai_description"] = "Descripción generada por IA"
        gen = DocGenerator(full_results)
        docs = gen._api_docs()
        assert docs[0]["description"] == "Descripción generada por IA"

    def test_sin_endpoints(self, minimal_results):
        gen = DocGenerator(minimal_results)
        docs = gen._api_docs()
        assert docs == []


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _api_section
# ─────────────────────────────────────────────────────────────────────────────

class TestApiSection:
    def test_sin_endpoints(self, minimal_results):
        gen = DocGenerator(minimal_results)
        section = gen._api_section()
        assert "No se detectaron endpoints" in section

    def test_con_endpoints(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._api_section()
        assert "GET" in section
        assert "POST" in section
        assert "/api/users" in section
        assert "Consulta o recupera" in section
        assert "Crea un recurso" in section

    def test_documenta_significado_de_todos_los_metodos_http(self, minimal_results):
        minimal_results["endpoints"] = [
            {"method": method, "path": "/api/resource"}
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE")
        ]
        section = DocGenerator(minimal_results)._api_section()
        for description in (
            "Consulta o recupera",
            "Crea un recurso",
            "Reemplaza o actualiza completamente",
            "Actualiza parcialmente",
            "Elimina el recurso",
        ):
            assert description in section

    def test_descripcion_get_y_metodos_larga_y_entendible(self, minimal_results):
        gen = DocGenerator(minimal_results, lang="es")
        # GET estándar
        get_desc = gen._http_method_description("GET", "/api/items")
        assert "Consulta o recupera" in get_desc
        assert "solo lectura" in get_desc.lower()
        assert len(get_desc) > 80  # Explicación completa y detallada

        # GET export/download
        get_export_desc = gen._http_method_description("GET", "/api/export/pdf")
        assert "descarga" in get_export_desc.lower()
        assert len(get_export_desc) > 80

        # POST, PUT, DELETE
        post_desc = gen._http_method_description("POST", "/api/items")
        assert "Crea un recurso" in post_desc
        assert len(post_desc) > 80

        put_desc = gen._http_method_description("PUT", "/api/items/1")
        assert "Reemplaza o actualiza completamente" in put_desc
        assert len(put_desc) > 80

    def test_infer_standalone_function_description_para_get_y_demas(self, minimal_results):
        gen = DocGenerator(minimal_results, lang="es")
        fn_get = {"name": "_get_project"}
        desc_get = gen._infer_standalone_function_description(fn_get)
        assert "consulta y lectura" in desc_get.lower()
        assert "project" in desc_get

        fn_create = {"name": "create_user"}
        desc_create = gen._infer_standalone_function_description(fn_create)
        assert "creación y registro" in desc_create.lower()
        assert "user" in desc_create

    def test_endpoint_description_detallada(self, minimal_results):
        gen = DocGenerator(minimal_results, lang="es")
        ep_get_list = {"method": "GET", "path": "/users"}
        desc_list = gen._generate_endpoint_description(ep_get_list)
        assert "users" in desc_list
        assert len(desc_list) > 50

        ep_get_item = {"method": "GET", "path": "/users/<user_id>"}
        desc_item = gen._generate_endpoint_description(ep_get_item)
        assert "users" in desc_item
        assert len(desc_item) > 50


    def test_incluye_setup(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._api_section()
        assert "3.1 Guía de Configuración" in section
        assert "git clone" in section

    def test_incluye_seccion_docstrings(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._api_section()
        assert "3.3 Estado de Comentarios" in section

    def test_incluye_planes_prueba(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._api_section()
        assert "3.4 Planes de Prueba" in section


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _class_docs
# ─────────────────────────────────────────────────────────────────────────────

class TestClassDocs:
    def test_devuelve_lista(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._class_docs()
        assert isinstance(docs, list)
        assert len(docs) == 2

    def test_estructura_de_cada_clase(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._class_docs()
        d = docs[0]
        assert "name" in d
        assert "file" in d
        assert "description" in d
        assert "methods" in d
        assert "method_count" in d

    def test_usa_ai_description_si_existe(self, full_results):
        full_results["classes"][0]["ai_description"] = "Descripción IA de clase"
        gen = DocGenerator(full_results)
        docs = gen._class_docs()
        assert docs[0]["description"] == "Descripción IA de clase"

    def test_usa_docstring_si_no_hay_ia(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._class_docs()
        assert docs[0]["description"] == "Modelo de usuario"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _classes_section
# ─────────────────────────────────────────────────────────────────────────────

class TestClassesSection:
    def test_sin_clases(self, minimal_results):
        gen = DocGenerator(minimal_results)
        section = gen._classes_section()
        assert "No se detectaron clases" in section

    def test_con_clases(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._classes_section()
        assert "UserModel" in section
        assert "bad_name" in section
        assert "Elimina el elemento relacionado" in section


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _function_docs
# ─────────────────────────────────────────────────────────────────────────────

class TestFunctionDocs:
    def test_devuelve_lista(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._function_docs()
        assert isinstance(docs, list)
        assert len(docs) == 4

    def test_estructura(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._function_docs()
        d = docs[0]
        assert "name" in d
        assert "file" in d
        assert "description" in d
        assert "parameters" in d
        assert "is_async" in d
        assert "complexity" in d

    def test_parametros_documentados(self, full_results):
        gen = DocGenerator(full_results)
        docs = gen._function_docs()
        # get_user tiene un param
        get_user = next(d for d in docs if d["name"] == "get_user")
        assert len(get_user["parameters"]) == 1
        assert get_user["parameters"][0]["name"] == "user_id"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _functions_section
# ─────────────────────────────────────────────────────────────────────────────

class TestFunctionsSection:
    def test_sin_funciones(self, minimal_results):
        gen = DocGenerator(minimal_results)
        section = gen._functions_section()
        assert "No se detectaron funciones" in section

    def test_con_funciones(self, full_results):
        full_results["functions"][0]["ai_description"] = "Obtiene el usuario solicitado"
        gen = DocGenerator(full_results)
        section = gen._functions_section()
        assert "get_user" in section
        assert "create_user" in section
        assert "Obtiene el usuario solicitado" in section

    def test_marca_funciones_async(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._functions_section()
        assert "`create_user` `[ASYNC]`" in section  # marca de funcion async

    def test_marca_alta_complejidad(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._functions_section()
        assert "HIGH (15)" in section  # complejidad alta (delete_user)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _data_models
# ─────────────────────────────────────────────────────────────────────────────

class TestDataModels:
    def test_detecta_modelos(self, full_results):
        gen = DocGenerator(full_results)
        section = gen._data_models()
        assert "UserModel" in section
        assert "1 modelos" in section or "modelos de datos" in section

    def test_sin_modelos_infiere_entidades(self, minimal_results):
        gen = DocGenerator(minimal_results)
        section = gen._data_models()
        assert "No se detectaron clases" in section

    def test_infiere_entidades_de_funciones(self):
        results = {
            "primary_language": "Python",
            "languages": {"Python": 1},
            "functions": [
                {"name": "get_user", "file": "a.py", "params": [], "docstring": ""},
                {"name": "create_order", "file": "a.py", "params": [], "docstring": ""},
                {"name": "delete_product", "file": "a.py", "params": [], "docstring": ""},
            ],
            "classes": [],
            "endpoints": [],
            "structure": [],
            "issues": [],
            "complexity": {"avg": 1, "max": 1, "high_complexity_funcs": 0},
            "quality_score": 70,
        }
        gen = DocGenerator(results)
        section = gen._data_models()
        assert "User" in section or "Order" in section or "Product" in section


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _generate_star_schema y _generate_snowflake_schema
# ─────────────────────────────────────────────────────────────────────────────

class TestDataWarehouseSchemas:
    def test_star_schema_sin_modelos(self, minimal_results):
        gen = DocGenerator(minimal_results)
        result = gen._generate_star_schema()
        assert result == ""

    def test_star_schema_con_modelos(self, full_results):
        gen = DocGenerator(full_results)
        # Mockeamos _generate_plantuml_diagram para que devuelva una URI
        with patch.object(gen, "_generate_plantuml_diagram", return_value="data:image/png;base64,XYZ"):
            result = gen._generate_star_schema()
            assert "data:image/png" in result
            assert "<img" in result

    def test_snowflake_requiere_3_modelos(self, full_results):
        gen = DocGenerator(full_results)
        # full_results solo tiene 1 modelo (UserModel) + bad_name no es modelo
        result = gen._generate_snowflake_schema()
        assert result == ""

    def test_snowflake_con_suficientes_modelos(self):
        results = {
            "primary_language": "Python",
            "languages": {"Python": 1},
            "total_files": 1,
            "functions": [],
            "classes": [
                {"name": "UserModel", "file": "m.py", "methods": ["save"], "bases": [], "docstring": ""},
                {"name": "OrderModel", "file": "m.py", "methods": ["create"], "bases": [], "docstring": ""},
                {"name": "ProductModel", "file": "m.py", "methods": ["update"], "bases": [], "docstring": ""},
                {"name": "CategoryModel", "file": "m.py", "methods": ["delete"], "bases": [], "docstring": ""},
            ],
            "endpoints": [],
            "structure": [],
            "issues": [],
            "complexity": {"avg": 1, "max": 1, "high_complexity_funcs": 0},
            "quality_score": 70,
        }
        gen = DocGenerator(results)
        with patch.object(gen, "_generate_plantuml_diagram", return_value="data:image/png;base64,XYZ"):
            result = gen._generate_snowflake_schema()
            assert "data:image/png" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _data_analysis_section
# ─────────────────────────────────────────────────────────────────────────────

class TestDataAnalysisSection:
    def test_incluye_secciones_principales(self, full_results):
        gen = DocGenerator(full_results)
        with patch("services.etl_pipeline.ETLPipeline") as MockETL:
            pipeline = MagicMock()
            pipeline.get_pipeline_diagram.return_value = "@startuml\n@enduml"
            MockETL.return_value = pipeline

            section = gen._data_analysis_section()
            assert "9. Análisis de Datos" in section
            assert "9.1" in section
            assert "9.2" in section
            assert "9.3" in section
            assert "9.4" in section
            assert "9.5" in section

    def test_detecta_alta_complejidad(self, full_results):
        gen = DocGenerator(full_results)
        with patch("services.etl_pipeline.ETLPipeline") as MockETL:
            MockETL.return_value.get_pipeline_diagram.return_value = "@startuml\n@enduml"
            section = gen._data_analysis_section()
            # delete_user tiene complejidad 15
            assert "delete_user" in section
            assert "Alta Complejidad" in section or "🔴" in section

    def test_detecta_sin_docstring(self, full_results):
        gen = DocGenerator(full_results)
        with patch("services.etl_pipeline.ETLPipeline") as MockETL:
            MockETL.return_value.get_pipeline_diagram.return_value = "@startuml\n@enduml"
            section = gen._data_analysis_section()
            # create_user no tiene docstring
            assert "create_user" in section
            assert "Sin Documentación" in section or "sin docstring" in section.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _deployment
# ─────────────────────────────────────────────────────────────────────────────

class TestDeployment:
    def test_incluye_docker(self, full_results):
        gen = DocGenerator(full_results)
        dep = gen._deployment()
        assert "Docker" in dep
        assert "python:3.12-slim" in dep

    def test_incluye_comandos_instalacion(self, full_results):
        gen = DocGenerator(full_results)
        dep = gen._deployment()
        assert "pip install -r requirements.txt" in dep

    def test_lenguaje_desconocido(self, minimal_results):
        minimal_results["primary_language"] = "COBOL"
        gen = DocGenerator(minimal_results)
        dep = gen._deployment()
        assert "ubuntu" in dep  # fallback docker

    def test_javascript(self):
        results = {
            "primary_language": "JavaScript",
            "languages": {"JavaScript": 1},
            "functions": [],
            "classes": [],
            "endpoints": [],
            "structure": [],
            "issues": [],
            "complexity": {"avg": 1, "max": 1, "high_complexity_funcs": 0},
            "quality_score": 70,
            "total_files": 1,
        }
        gen = DocGenerator(results)
        dep = gen._deployment()
        assert "npm install" in dep
        assert "node:20-slim" in dep


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _quality_report
# ─────────────────────────────────────────────────────────────────────────────

class TestQualityReport:
    def test_score_alto(self):
        results = {
            "primary_language": "Python",
            "languages": {"Python": 1},
            "functions": [{"name": "f1", "docstring": "doc", "complexity": 2, "file": "a.py"}],
            "classes": [],
            "endpoints": [],
            "structure": [],
            "issues": [],
            "complexity": {"avg": 1.5, "max": 2, "high_complexity_funcs": 0},
            "quality_score": 85,
        }
        gen = DocGenerator(results)
        report = gen._quality_report()
        assert "85/100" in report
        assert "Excelente" in report

    def test_score_bajo(self, full_results):
        gen = DocGenerator(full_results)
        report = gen._quality_report()
        assert "65/100" in report
        assert "Bueno" in report

    def test_detecta_funciones_alta_complejidad(self, full_results):
        gen = DocGenerator(full_results)
        report = gen._quality_report()
        # delete_user tiene complejidad 15
        assert "delete_user" in report or "alta complejidad" in report.lower()

    def test_incluye_issues(self, full_results):
        gen = DocGenerator(full_results)
        report = gen._quality_report()
        assert "Syntax error" in report or "Errores" in report

    def test_sin_problemas(self, minimal_results):
        gen = DocGenerator(minimal_results)
        report = gen._quality_report()
        assert "Sin errores detectados" in report or "OK" in report


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _full_markdown (integración)
# ─────────────────────────────────────────────────────────────────────────────

class TestFullMarkdown:
    def test_contiene_todas_las_secciones(self, full_results):
        gen = DocGenerator(full_results)
        with patch("services.etl_pipeline.ETLPipeline") as MockETL:
            MockETL.return_value.get_pipeline_diagram.return_value = "@startuml\n@enduml"
            md = gen._full_markdown()
            assert "# Documentación del Proyecto" in md
            assert "2. Documentación de Arquitectura" in md
            assert "4. Documentación de Clases y Módulos" in md
            assert "5. Documentación de Funciones" in md
            assert "7. Guía de Despliegue" in md
            assert "8. Reporte de Calidad" in md
            assert "9. Análisis de Datos" in md

    def test_termina_con_firma(self, full_results):
        gen = DocGenerator(full_results)
        with patch("services.etl_pipeline.ETLPipeline") as MockETL:
            MockETL.return_value.get_pipeline_diagram.return_value = "@startuml\n@enduml"
            md = gen._full_markdown()
            assert "AutoDocs AI" in md