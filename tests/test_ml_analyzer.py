"""
tests/test_ml_analyzer.py

Tests unitarios para services/ml_analyzer.py
Ejecutar con: pytest
"""

import pytest
import numpy as np

from services.ml_analyzer import (
    _extract_features,
    _extract_project_type_features,
    _assign_domain_label,
    build_training_dataset,
    linear_regression_simple,
    linear_regression_multiple,
    logistic_regression,
    mean_absolute_error_analysis,
    pca_analysis,
    decision_tree_classifier,
    classify_project_type,
    run_ml_analysis,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: datos de ejemplo que simulan la salida de ProjectAnalyzer.analyze()
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_results():
    """Resultado simulado de ProjectAnalyzer.analyze() para un proyecto tipo API."""
    return {
        "total_files": 10,
        "functions": [
            {"name": "get_user", "docstring": "Obtiene usuario", "is_async": True, "size": 200},
            {"name": "create_user", "docstring": None, "is_async": False, "size": 300},
            {"name": "delete_user", "docstring": "Elimina usuario", "is_async": False, "size": 150},
            {"name": "test_login", "docstring": "Test de login", "is_async": True, "size": 100},
        ],
        "classes": [
            {"name": "UserController"},
            {"name": "UserService"},
        ],
        "endpoints": [
            {"path": "/api/users", "method": "GET"},
            {"path": "/api/users", "method": "POST"},
            {"path": "/api/users/{id}", "method": "DELETE"},
        ],
        "issues": [
            {"type": "bug", "line": 10},
            {"type": "warning", "line": 20},
        ],
        "languages": {"Python": 900, "JavaScript": 100},
        "complexity": {"avg": 3.5, "max": 8, "high_complexity_funcs": 1},
        "quality_score": 72,
        "structure": [
            {"name": "user_controller.py", "size": 500},
            {"name": "user_service.py", "size": 400},
            {"name": "models.py", "size": 300},
        ],
    }


@pytest.fixture
def sample_features(sample_results):
    """Features extraídas del sample_results."""
    return _extract_features(sample_results)


@pytest.fixture
def all_projects_data():
    """Lista simulada de todos los proyectos para entrenar el árbol de decisión."""
    projects = []
    for i in range(15):
        results = {
            "total_files": 5 + i,
            "functions": [
                {"name": f"patient_function_{i}", "docstring": "doc", "is_async": False, "size": 100},
                {"name": f"hospital_handler_{i}", "docstring": None, "is_async": False, "size": 120},
            ],
            "classes": [{"name": "MedicalRecord"}],
            "endpoints": [{"path": "/patients", "method": "GET"}],
            "issues": [],
            "languages": {"Python": 500},
            "complexity": {"avg": 2.0, "max": 4, "high_complexity_funcs": 0},
            "quality_score": 80,
            "structure": [{"name": "patient.py", "size": 200}],
        }
        projects.append({"results": results, "project": {"name": f"Proyecto {i}"}})
    return projects


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _extract_features
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractFeatures:
    def test_extrae_metricas_basicas(self, sample_results):
        feats = _extract_features(sample_results)
        assert feats["total_files"] == 10
        assert feats["total_funcs"] == 4
        assert feats["total_classes"] == 2
        assert feats["total_endpoints"] == 3
        assert feats["total_issues"] == 2
        assert feats["total_langs"] == 2

    def test_calcula_doc_ratio(self, sample_results):
        feats = _extract_features(sample_results)
        # 3 de 4 funciones tienen docstring
        assert feats["doc_ratio"] == pytest.approx(0.75, rel=1e-3)

    def test_cuenta_funciones_async_y_tests(self, sample_results):
        feats = _extract_features(sample_results)
        assert feats["async_funcs"] == 2
        assert feats["test_funcs"] == 1  # "test_login"

    def test_extrae_func_names(self, sample_results):
        feats = _extract_features(sample_results)
        assert "get_user" in feats["func_names"]
        assert len(feats["func_names"]) == 4

    def test_results_vacio_no_falla(self):
        feats = _extract_features({})
        assert feats["total_files"] == 0
        assert feats["total_funcs"] == 0
        assert feats["doc_ratio"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _assign_domain_label
# ─────────────────────────────────────────────────────────────────────────────

class TestAssignDomainLabel:
    def test_dominio_medico(self):
        scores = {"medico": 10, "financiero": 1, "educativo": 0, "comercio": 0, "api": 2}
        assert _assign_domain_label(scores) == "Medico/Salud"

    def test_dominio_financiero(self):
        scores = {"medico": 0, "financiero": 8, "educativo": 1, "comercio": 0, "api": 1}
        assert _assign_domain_label(scores) == "Financiero"

    def test_dominio_otro_por_umbral_bajo(self):
        scores = {"medico": 1, "financiero": 1, "educativo": 1, "comercio": 1, "api": 1}
        assert _assign_domain_label(scores, threshold=3) == "Otro"

    def test_dominio_otro_scores_vacios(self):
        assert _assign_domain_label({}) == "Otro"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _extract_project_type_features
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractProjectTypeFeatures:
    def test_detecta_keywords_api(self, sample_results):
        feats = _extract_features(sample_results)
        pt = _extract_project_type_features(sample_results, feats)
        assert "domain_scores" in pt
        assert pt["domain_scores"]["api"] >= 0

    def test_detecta_models_y_services(self, sample_results):
        pt = _extract_project_type_features(sample_results)
        # "user_service.py" contiene 'service'
        assert pt["has_services"] is True

    def test_estructura_retornada(self, sample_results):
        pt = _extract_project_type_features(sample_results)
        claves = ["domain_scores", "total_funcs", "total_endpoints",
                  "doc_ratio", "avg_complexity", "has_tests",
                  "has_models", "has_views", "has_controllers", "has_services"]
        for k in claves:
            assert k in pt


# ─────────────────────────────────────────────────────────────────────────────
# Tests: build_training_dataset
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildTrainingDataset:
    def test_construye_dataset(self, all_projects_data):
        X, y, names, labels = build_training_dataset(all_projects_data)
        assert X.shape[0] == len(all_projects_data)
        assert y.shape[0] == len(all_projects_data)
        assert len(names) == len(all_projects_data)
        assert "Medico/Salud" in labels

    def test_dataset_vacio(self):
        X, y, names, labels = build_training_dataset([])
        assert len(X) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: linear_regression_simple
# ─────────────────────────────────────────────────────────────────────────────

class TestLinearRegressionSimple:
    def test_devuelve_estructura_esperada(self, sample_features):
        res = linear_regression_simple(sample_features)
        claves = ["tipo", "coeficiente", "intercepto", "r2", "mae",
                  "prediccion_proyecto_actual", "puntos", "interpretacion", "sugerencias"]
        for k in claves:
            assert k in res, f"Falta clave: {k}"

    def test_tipo_correcto(self, sample_features):
        res = linear_regression_simple(sample_features)
        assert res["tipo"] == "Regresión Lineal Simple"

    def test_r2_en_rango(self, sample_features):
        res = linear_regression_simple(sample_features)
        assert 0 <= res["r2"] <= 1

    def test_prediccion_entre_0_y_100(self, sample_features):
        res = linear_regression_simple(sample_features)
        assert 0 <= res["prediccion_proyecto_actual"] <= 100

    def test_puntos_generados(self, sample_features):
        res = linear_regression_simple(sample_features)
        assert len(res["puntos"]) == 20


# ─────────────────────────────────────────────────────────────────────────────
# Tests: linear_regression_multiple
# ─────────────────────────────────────────────────────────────────────────────

class TestLinearRegressionMultiple:
    def test_devuelve_coeficientes(self, sample_features):
        res = linear_regression_multiple(sample_features)
        assert "coeficientes" in res
        assert "Funciones" in res["coeficientes"]
        assert "Complejidad promedio" in res["coeficientes"]
        assert "Issues" in res["coeficientes"]
        assert "Tests" in res["coeficientes"]
        assert "Endpoints" in res["coeficientes"]

    def test_tipo_correcto(self, sample_features):
        res = linear_regression_multiple(sample_features)
        assert res["tipo"] == "Regresión Lineal Múltiple"

    def test_muestra_datos(self, sample_features):
        res = linear_regression_multiple(sample_features)
        assert len(res["muestra_datos"]) == 5

    def test_r2_valido(self, sample_features):
        res = linear_regression_multiple(sample_features)
        assert 0 <= res["r2"] <= 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests: logistic_regression
# ─────────────────────────────────────────────────────────────────────────────

class TestLogisticRegression:
    def test_metricas_presentes(self, sample_features):
        res = logistic_regression(sample_features)
        for k in ["accuracy", "precision", "recall", "f1_score", "prob_documentada_actual"]:
            assert k in res

    def test_matriz_confusion(self, sample_features):
        res = logistic_regression(sample_features)
        cm = res["matriz_confusion"]
        assert set(cm.keys()) == {"TP", "TN", "FP", "FN"}

    def test_probabilidad_en_rango(self, sample_features):
        res = logistic_regression(sample_features)
        assert 0 <= res["prob_documentada_actual"] <= 1

    def test_tipo_correcto(self, sample_features):
        res = logistic_regression(sample_features)
        assert res["tipo"] == "Regresión Logística"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: mean_absolute_error_analysis
# ─────────────────────────────────────────────────────────────────────────────

class TestMeanAbsoluteErrorAnalysis:
    def test_devuelve_modelos(self, sample_features):
        res = mean_absolute_error_analysis(sample_features)
        assert "modelos" in res
        assert len(res["modelos"]) >= 2  # simple y múltiple

    def test_quality_score_real(self, sample_features):
        res = mean_absolute_error_analysis(sample_features)
        assert res["quality_score_real"] == sample_features["quality_score"]

    def test_mae_promedio(self, sample_features):
        res = mean_absolute_error_analysis(sample_features)
        assert res["mae_promedio_regresion"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: pca_analysis
# ─────────────────────────────────────────────────────────────────────────────

class TestPCAAnalysis:
    def test_pca_con_pocos_proyectos(self, sample_results):
        analyses = [{"results": sample_results, "project_id": "p1"}]
        res = pca_analysis(analyses)
        assert "error" in res  # se requieren al menos 2

    def test_pca_con_dos_proyectos(self, sample_results):
        analyses = [
            {"results": sample_results, "project_id": "p1"},
            {"results": sample_results, "project_id": "p2"},
        ]
        res = pca_analysis(analyses)
        assert "project_coordinates" in res
        assert len(res["project_coordinates"]) == 2
        assert "explained_variance_ratio" in res

    def test_pca_devuelve_conclusiones(self, sample_results):
        analyses = [
            {"results": sample_results, "project_id": f"p{i}"} for i in range(4)
        ]
        res = pca_analysis(analyses)
        assert "conclusion" in res
        assert "sugerencias" in res


# ─────────────────────────────────────────────────────────────────────────────
# Tests: decision_tree_classifier
# ─────────────────────────────────────────────────────────────────────────────

class TestDecisionTreeClassifier:
    def test_clasificacion_retorna_estructura(self, sample_results):
        feats = _extract_features(sample_results)
        pt_feats = _extract_project_type_features(sample_results, feats)
        res = decision_tree_classifier(feats, pt_feats)

        claves = ["tipo", "clasificacion", "confianza", "probabilidades",
                  "caracteristicas_importantes", "interpretacion", "recomendaciones"]
        for k in claves:
            assert k in res, f"Falta clave: {k}"

    def test_clasificacion_en_categorias_validas(self, sample_results):
        feats = _extract_features(sample_results)
        pt_feats = _extract_project_type_features(sample_results, feats)
        res = decision_tree_classifier(feats, pt_feats)

        categorias = ["Medico/Salud", "Financiero", "Educativo",
                      "Comercio", "API/REST", "Otro"]
        assert res["clasificacion"] in categorias

    def test_confianza_en_rango(self, sample_results):
        feats = _extract_features(sample_results)
        pt_feats = _extract_project_type_features(sample_results, feats)
        res = decision_tree_classifier(feats, pt_feats)
        assert 0 <= res["confianza"] <= 100

    def test_modo_sintetico_sin_datos_reales(self, sample_results):
        feats = _extract_features(sample_results)
        pt_feats = _extract_project_type_features(sample_results, feats)
        res = decision_tree_classifier(feats, pt_feats, all_projects_data=None)
        assert "sintéticos" in res["fuente_datos"]

    def test_modo_real_con_suficientes_datos(self, sample_results, all_projects_data):
        feats = _extract_features(sample_results)
        pt_feats = _extract_project_type_features(sample_results, feats)
        res = decision_tree_classifier(
            feats, pt_feats,
            all_projects_data=all_projects_data,
            min_real_samples=12,
            min_real_classes=2,
        )
        # Con 15 proyectos del mismo dominio, debería usar datos reales
        assert "reales" in res["fuente_datos"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: classify_project_type (wrapper)
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifyProjectType:
    def test_wrapper_funciona(self, sample_results):
        project = {"name": "Proyecto Demo"}
        res = classify_project_type(sample_results, project)
        assert "clasificacion" in res
        assert "confianza" in res


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_ml_analysis (función principal)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunMLAnalysis:
    def test_devuelve_todos_los_modelos(self, sample_results):
        res = run_ml_analysis(sample_results)
        for k in ["features", "regresion_simple", "regresion_multiple",
                  "regresion_logistica", "mae_analysis", "arbol_decision"]:
            assert k in res, f"Falta clave: {k}"

    def test_features_correctas(self, sample_results):
        res = run_ml_analysis(sample_results)
        assert res["features"]["total_funcs"] == 4

    def test_con_all_projects_data(self, sample_results, all_projects_data):
        res = run_ml_analysis(sample_results, all_projects_data=all_projects_data)
        assert "arbol_decision" in res
        assert "clasificacion" in res["arbol_decision"]