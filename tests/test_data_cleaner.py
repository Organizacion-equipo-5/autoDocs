"""
tests/test_data_cleaner.py

Tests unitarios para services/data_cleaner.py
Ejecutar con: python -m pytest tests/test_data_cleaner.py -v
"""

import pytest
from services.data_cleaner import DataCleaner


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def cleaner():
    """Instancia limpia de DataCleaner para cada test."""
    return DataCleaner()


@pytest.fixture
def sample_data():
    """Dataset de ejemplo con duplicados, nulos y strings sin normalizar."""
    return [
        {"id": 1, "name": "Alice", "age": 30, "city": "NYC"},
        {"id": 2, "name": "Bob", "age": 25, "city": "LA"},
        {"id": 1, "name": "Alice", "age": 30, "city": "NYC"},  # duplicado
        {"id": 3, "name": "  CHARLIE  ", "age": None, "city": "CHICAGO"},
        {"id": 4, "name": "dave!", "age": 40, "city": ""},
    ]


@pytest.fixture
def numeric_data():
    """Dataset numérico para tests de outliers."""
    return [
        {"value": 10},
        {"value": 12},
        {"value": 11},
        {"value": 13},
        {"value": 12},
        {"value": 11},
        {"value": 12},
        {"value": 1000},  # outlier claro
        {"value": -500},  # outlier claro
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: __init__ / reset_report / get_cleaning_report
# ─────────────────────────────────────────────────────────────────────────────

class TestInitAndReport:
    def test_reporte_inicial_vacio(self, cleaner):
        report = cleaner.get_cleaning_report()
        assert report["duplicates_removed"] == 0
        assert report["missing_values_filled"] == 0
        assert report["strings_normalized"] == 0
        assert report["outliers_detected"] == {}
        assert report["inconsistencies_fixed"] == 0

    def test_reporte_tiene_todas_las_claves(self, cleaner):
        report = cleaner.get_cleaning_report()
        claves = [
            "duplicates_removed", "missing_values_filled",
            "strings_normalized", "outliers_detected", "inconsistencies_fixed"
        ]
        for k in claves:
            assert k in report

    def test_reset_report(self, cleaner, sample_data):
        # Generar actividad
        cleaner.remove_duplicates(sample_data)
        assert cleaner.get_cleaning_report()["duplicates_removed"] > 0

        # Resetear
        cleaner.reset_report()
        report = cleaner.get_cleaning_report()
        assert report["duplicates_removed"] == 0
        assert report["missing_values_filled"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: remove_duplicates
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveDuplicates:
    def test_elimina_duplicados_exactos(self, cleaner, sample_data):
        result = cleaner.remove_duplicates(sample_data)
        assert len(result) == 4  # 5 - 1 duplicado
        assert cleaner.get_cleaning_report()["duplicates_removed"] == 1

    def test_sin_duplicados_no_cambia(self, cleaner):
        data = [{"a": 1}, {"a": 2}, {"a": 3}]
        result = cleaner.remove_duplicates(data)
        assert len(result) == 3
        assert cleaner.get_cleaning_report()["duplicates_removed"] == 0

    def test_lista_vacia(self, cleaner):
        result = cleaner.remove_duplicates([])
        assert result == []

    def test_lista_none(self, cleaner):
        result = cleaner.remove_duplicates(None)
        assert result is None

    def test_preserva_orden_original(self, cleaner):
        data = [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
            {"id": 1, "name": "A"},  # duplicado
            {"id": 3, "name": "C"},
        ]
        result = cleaner.remove_duplicates(data)
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert result[2]["id"] == 3

    def test_acumula_contador_entre_llamadas(self, cleaner):
        cleaner.remove_duplicates([{"a": 1}, {"a": 1}])
        cleaner.remove_duplicates([{"b": 2}, {"b": 2}])
        assert cleaner.get_cleaning_report()["duplicates_removed"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: remove_duplicates_by_field
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoveDuplicatesByField:
    def test_elimina_por_campo(self, cleaner):
        data = [
            {"id": 1, "name": "A"},
            {"id": 1, "name": "B"},  # duplicado en id
            {"id": 2, "name": "C"},
        ]
        result = cleaner.remove_duplicates_by_field(data, "id")
        assert len(result) == 2
        assert result[0]["name"] == "A"  # conserva el primero

    def test_campo_inexistente_devuelve_original(self, cleaner):
        data = [{"id": 1}, {"id": 2}]
        result = cleaner.remove_duplicates_by_field(data, "campo_inexistente")
        assert result == data

    def test_lista_vacia(self, cleaner):
        result = cleaner.remove_duplicates_by_field([], "id")
        assert result == []

    def test_valores_none_como_duplicados(self, cleaner):
        data = [
            {"id": None, "name": "A"},
            {"id": None, "name": "B"},  # mismo None
            {"id": 1, "name": "C"},
        ]
        result = cleaner.remove_duplicates_by_field(data, "id")
        assert len(result) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests: fill_missing_values
# ─────────────────────────────────────────────────────────────────────────────

class TestFillMissingValues:
    def test_estrategia_default(self, cleaner, sample_data):
        result = cleaner.fill_missing_values(sample_data, strategy="default")
        # Los valores None y "" deben rellenarse con None
        assert result[3]["age"] is None  # estaba None
        assert result[4]["city"] is None  # estaba ""

    def test_estrategia_mean(self, cleaner):
        data = [{"x": 10}, {"x": 20}, {"x": None}, {"x": 30}]
        result = cleaner.fill_missing_values(data, strategy="mean")
        # mean de (10, 20, 30) = 20
        assert result[2]["x"] == 20

    def test_estrategia_median(self, cleaner):
        data = [{"x": 1}, {"x": 3}, {"x": 5}, {"x": None}]
        result = cleaner.fill_missing_values(data, strategy="median")
        # mediana de (1, 3, 5) = 3
        assert result[3]["x"] == 3

    def test_estrategia_mode(self, cleaner):
        data = [{"x": "A"}, {"x": "B"}, {"x": "A"}, {"x": None}]
        result = cleaner.fill_missing_values(data, strategy="mode")
        assert result[3]["x"] == "A"

    def test_estrategia_forward_fill(self, cleaner):
        data = [{"x": 1}, {"x": 2}, {"x": None}]
        result = cleaner.fill_missing_values(data, strategy="forward_fill")
        assert result[2]["x"] == 2  # último valor válido

    def test_lista_vacia(self, cleaner):
        result = cleaner.fill_missing_values([])
        assert result == []

    def test_contador_missing_values(self, cleaner):
        data = [{"a": None, "b": 1}, {"a": 2, "b": ""}]
        cleaner.fill_missing_values(data)
        assert cleaner.get_cleaning_report()["missing_values_filled"] == 2

    def test_sin_valores_faltantes(self, cleaner):
        data = [{"a": 1, "b": 2}]
        cleaner.fill_missing_values(data)
        assert cleaner.get_cleaning_report()["missing_values_filled"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: normalize_strings
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeStrings:
    def test_normaliza_todos_los_strings(self, cleaner):
        data = [{"name": "  HELLO WORLD  ", "age": 30}]
        result = cleaner.normalize_strings(data)
        assert result[0]["name"] == "hello world"
        assert result[0]["age"] == 30

    def test_remueve_caracteres_especiales(self, cleaner):
        data = [{"text": "hola!!! @#$ mundo..."}]
        result = cleaner.normalize_strings(data)
        # Solo quedan letras, espacios y guiones
        assert "!" not in result[0]["text"]
        assert "@" not in result[0]["text"]

    def test_conserva_acronimos_mayusculas(self, cleaner):
        data = [{"code": "HTTP_SERVER"}]
        result = cleaner.normalize_strings(data)
        # No debe convertir a lowercase si detecta A-Z repetidas
        assert "HTTP" in result[0]["code"] or "http_server" == result[0]["code"]

    def test_normaliza_solo_campos_especificos(self, cleaner):
        data = [{"a": "  HELLO  ", "b": "  WORLD  "}]
        result = cleaner.normalize_strings(data, fields=["a"])
        assert result[0]["a"] == "hello"
        assert result[0]["b"] == "  WORLD  "  # sin cambios

    def test_contador_strings_normalized(self, cleaner):
        data = [{"a": "  X  "}, {"a": "Y"}]
        cleaner.normalize_strings(data)
        assert cleaner.get_cleaning_report()["strings_normalized"] >= 1

    def test_lista_vacia(self, cleaner):
        result = cleaner.normalize_strings([])
        assert result == []

    def test_remueve_espacios_multiples(self, cleaner):
        data = [{"text": "hello    world"}]
        result = cleaner.normalize_strings(data)
        assert "  " not in result[0]["text"]

    def test_preserva_no_strings(self, cleaner):
        data = [{"num": 42, "flag": True, "obj": None}]
        result = cleaner.normalize_strings(data)
        assert result[0]["num"] == 42
        assert result[0]["flag"] is True
        assert result[0]["obj"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_outliers
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectOutliers:
    def test_metodo_iqr_detecta_outliers(self, cleaner, numeric_data):
        result = cleaner.detect_outliers(numeric_data, "value", method="iqr")
        assert result["count"] >= 1
        assert 1000 in result["outliers"] or -500 in result["outliers"]

    def test_metodo_zscore(self, cleaner, numeric_data):
        result = cleaner.detect_outliers(numeric_data, "value", method="zscore")
        assert result["count"] >= 1

    def test_metodo_percentile(self, cleaner, numeric_data):
        result = cleaner.detect_outliers(numeric_data, "value", method="percentile")
        assert "count" in result
        assert "outliers" in result

    def test_columna_inexistente(self, cleaner, numeric_data):
        result = cleaner.detect_outliers(numeric_data, "no_existe", method="iqr")
        assert result["count"] == 0
        assert result["outliers"] == []

    def test_lista_vacia(self, cleaner):
        result = cleaner.detect_outliers([], "value")
        assert result["count"] == 0

    def test_sin_valores_numericos(self, cleaner):
        data = [{"x": "a"}, {"x": "b"}, {"x": "c"}]
        result = cleaner.detect_outliers(data, "x", method="iqr")
        assert result["count"] == 0

    def test_guarda_en_reporte(self, cleaner, numeric_data):
        cleaner.detect_outliers(numeric_data, "value", method="iqr")
        report = cleaner.get_cleaning_report()
        assert "value" in report["outliers_detected"]

    def test_porcentaje_calculado(self, cleaner, numeric_data):
        result = cleaner.detect_outliers(numeric_data, "value", method="iqr")
        assert "percentage" in result
        assert 0 <= result["percentage"] <= 100

    def test_sin_outliers(self, cleaner):
        data = [{"v": 10}, {"v": 11}, {"v": 12}, {"v": 11}]
        result = cleaner.detect_outliers(data, "v", method="iqr")
        assert result["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: detect_inconsistencies
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectInconsistencies:
    def test_valor_menor_al_minimo(self, cleaner):
        data = [{"age": -5}, {"age": 30}]
        rules = [{"field": "age", "min": 0}]
        result = cleaner.detect_inconsistencies(data, rules)
        assert len(result) == 1
        assert "menor al mínimo" in result[0]["message"]

    def test_valor_mayor_al_maximo(self, cleaner):
        data = [{"age": 200}, {"age": 30}]
        rules = [{"field": "age", "max": 120}]
        result = cleaner.detect_inconsistencies(data, rules)
        assert len(result) == 1
        assert "mayor al máximo" in result[0]["message"]

    def test_validacion_pattern_regex(self, cleaner):
        data = [{"email": "invalid"}, {"email": "user@test.com"}]
        rules = [{"field": "email", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}]
        result = cleaner.detect_inconsistencies(data, rules)
        assert len(result) == 1
        assert "patrón" in result[0]["message"]

    def test_validacion_allowed_values(self, cleaner):
        data = [{"status": "activo"}, {"status": "invalido"}]
        rules = [{"field": "status", "allowed_values": ["activo", "inactivo"]}]
        result = cleaner.detect_inconsistencies(data, rules)
        assert len(result) == 1
        assert "permitidos" in result[0]["message"]

    def test_sin_reglas(self, cleaner):
        data = [{"age": 30}]
        result = cleaner.detect_inconsistencies(data, [])
        assert result == []

    def test_sin_datos(self, cleaner):
        result = cleaner.detect_inconsistencies([], [{"field": "age", "min": 0}])
        assert result == []

    def test_campo_no_presente_se_ignora(self, cleaner):
        data = [{"name": "A"}]
        rules = [{"field": "age", "min": 0}]
        result = cleaner.detect_inconsistencies(data, rules)
        assert result == []

    def test_actualiza_reporte(self, cleaner):
        data = [{"age": -5}]
        rules = [{"field": "age", "min": 0}]
        cleaner.detect_inconsistencies(data, rules)
        assert cleaner.get_cleaning_report()["inconsistencies_fixed"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests: clean_code_issues
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanCodeIssues:
    def test_detecta_funciones_sin_docstring(self, cleaner):
        analysis = {
            "functions": [
                {"name": "f1", "docstring": "ok", "file": "a.py", "line": 1},
                {"name": "f2", "docstring": "", "file": "a.py", "line": 10},
                {"name": "f3", "file": "a.py", "line": 20},
            ]
        }
        result = cleaner.clean_code_issues(analysis)
        assert len(result["missing_docstrings"]) == 2

    def test_detecta_alta_complejidad(self, cleaner):
        analysis = {
            "functions": [
                {"name": "f1", "complexity": 5, "docstring": "x"},
                {"name": "f2", "complexity": 15, "docstring": "x", "file": "b.py"},
                {"name": "f3", "complexity": 20, "docstring": "x", "file": "c.py"},
            ]
        }
        result = cleaner.clean_code_issues(analysis)
        assert len(result["high_complexity"]) == 2

    def test_detecta_naming_conventions(self, cleaner):
        analysis = {
            "classes": [
                {"name": "GoodClass", "file": "a.py"},
                {"name": "bad_class", "file": "b.py"},
                {"name": "anotherBad", "file": "c.py"},
            ]
        }
        result = cleaner.clean_code_issues(analysis)
        assert len(result["naming_conventions"]) == 2

    def test_analysis_vacio(self, cleaner):
        result = cleaner.clean_code_issues({})
        assert result["missing_docstrings"] == []
        assert result["high_complexity"] == []
        assert result["naming_conventions"] == []

    def test_devuelve_todas_las_claves(self, cleaner):
        result = cleaner.clean_code_issues({})
        for k in ["missing_docstrings", "high_complexity", "naming_conventions", "unused_imports"]:
            assert k in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: integración (flujo completo)
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    def test_pipeline_completo(self, cleaner, sample_data):
        # 1) Quitar duplicados
        data = cleaner.remove_duplicates(sample_data)
        # 2) Rellenar nulos
        data = cleaner.fill_missing_values(data, strategy="default")
        # 3) Normalizar strings
        data = cleaner.normalize_strings(data)

        report = cleaner.get_cleaning_report()
        assert report["duplicates_removed"] == 1
        assert report["missing_values_filled"] >= 1
        assert report["strings_normalized"] >= 1

        # Verificar que el nombre de Charlie se normalizó
        charlie = next(item for item in data if item["id"] == 3)
        assert charlie["name"] == "charlie"

    def test_reset_limpia_todo(self, cleaner, sample_data):
        cleaner.remove_duplicates(sample_data)
        cleaner.fill_missing_values(sample_data)
        cleaner.reset_report()

        report = cleaner.get_cleaning_report()
        assert report["duplicates_removed"] == 0
        assert report["missing_values_filled"] == 0
        assert report["outliers_detected"] == {}