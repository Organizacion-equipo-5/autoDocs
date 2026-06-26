"""
services/ml_analyzer.py

Servicio de predicciones y estadísticas para autoDocs.
Coloca este archivo en: autoDocs/backend/services/ml_analyzer.py

Instala las dependencias nuevas:
    pip install scikit-learn pandas numpy matplotlib seaborn
"""

import numpy as np
from typing import Optional


# ─── Helpers internos ────────────────────────────────────────────────────────

def _safe_import():
    """Intenta importar scikit-learn; retorna False si no está instalado."""
    try:
        import sklearn  # noqa: F401
        import pandas   # noqa: F401
        return True
    except ImportError:
        return False


def _extract_features(results: dict) -> dict:
    """
    Extrae todas las métricas del resultado del ProjectAnalyzer
    y las convierte en variables numéricas listas para ML.
    """
    funcs      = results.get("functions", [])
    classes    = results.get("classes", [])
    endpoints  = results.get("endpoints", [])
    issues     = results.get("issues", [])
    languages  = results.get("languages", {})
    complexity = results.get("complexity", {})

    total_files    = results.get("total_files", 0)
    total_funcs    = len(funcs)
    total_classes  = len(classes)
    total_endpoints = len(endpoints)
    total_issues   = len(issues)
    total_langs    = len(languages)

    documented     = sum(1 for f in funcs if f.get("docstring"))
    doc_ratio      = round(documented / max(total_funcs, 1), 4)

    async_funcs    = sum(1 for f in funcs if f.get("is_async"))
    test_funcs     = sum(1 for f in funcs if "test" in f.get("name", "").lower())

    avg_complexity = complexity.get("avg", 1.0)
    max_complexity = complexity.get("max", 1)
    high_cx_funcs  = complexity.get("high_complexity_funcs", 0)

    quality_score  = results.get("quality_score", 50)

    # Tamaño total estimado (suma de bytes de estructura)
    total_size = sum(f.get("size", 0) for f in results.get("structure", []))

    return {
        "total_files":     total_files,
        "total_funcs":     total_funcs,
        "total_classes":   total_classes,
        "total_endpoints": total_endpoints,
        "total_issues":    total_issues,
        "total_langs":     total_langs,
        "doc_ratio":       doc_ratio,
        "async_funcs":     async_funcs,
        "test_funcs":      test_funcs,
        "avg_complexity":  avg_complexity,
        "max_complexity":  max_complexity,
        "high_cx_funcs":   high_cx_funcs,
        "quality_score":   quality_score,
        "total_size_kb":   round(total_size / 1024, 2),
    }


# ─── Regresión lineal simple ──────────────────────────────────────────────────

def linear_regression_simple(features: dict) -> dict:
    """
    Regresión lineal simple:
      X = número de funciones
      y = calidad estimada de documentación (0-100)

    Genera 20 puntos sintéticos escalados a partir de las métricas reales
    del proyecto para trazar la línea de tendencia.
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado. Ejecuta: pip install scikit-learn pandas numpy"}

    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    n_funcs   = max(features["total_funcs"], 1)
    doc_ratio = features["doc_ratio"]

    # Generamos puntos sintéticos realistas alrededor del proyecto actual
    rng = np.random.default_rng(seed=42)
    X_vals = np.linspace(max(1, n_funcs * 0.2), n_funcs * 2.5, 20)
    # Relación inversa suavizada: más funciones → ratio docs tiende a bajar
    noise  = rng.normal(0, 5, 20)
    y_vals = np.clip(100 * doc_ratio - (X_vals - n_funcs) * 0.4 + noise, 0, 100)

    X = X_vals.reshape(-1, 1)
    y = y_vals

    model = LinearRegression()
    model.fit(X, y)

    y_pred  = model.predict(X)
    mae     = round(mean_absolute_error(y, y_pred), 2)
    r2      = round(model.score(X, y), 4)
    pred_actual = round(float(model.predict([[n_funcs]])[0]), 2)

    return {
        "tipo": "Regresión Lineal Simple",
        "variable_x": "Número de funciones",
        "variable_y": "Calidad de documentación (%)",
        "coeficiente": round(float(model.coef_[0]), 4),
        "intercepto":  round(float(model.intercept_), 4),
        "r2":          r2,
        "mae":         mae,
        "prediccion_proyecto_actual": pred_actual,
        "puntos": [
            {"x": round(float(x), 1), "y_real": round(float(yr), 2), "y_pred": round(float(yp), 2)}
            for x, yr, yp in zip(X_vals, y_vals, y_pred)
        ],
        "interpretacion": (
            f"Por cada función adicional, la calidad de documentación cambia "
            f"{round(float(model.coef_[0]), 2)} puntos. "
            f"El modelo explica el {round(r2 * 100, 1)}% de la varianza (R²={r2}). "
            f"Error absoluto medio: {mae} puntos."
        ),
    }


# ─── Regresión lineal múltiple ────────────────────────────────────────────────

def linear_regression_multiple(features: dict) -> dict:
    """
    Regresión lineal múltiple:
      Variables X: [total_funcs, avg_complexity, total_issues, test_funcs, total_endpoints]
      Variable y:  quality_score (0-100)
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    rng = np.random.default_rng(seed=7)

    base_quality  = features["quality_score"]
    base_cx       = max(features["avg_complexity"], 1.0)
    base_issues   = features["total_issues"]
    base_tests    = features["test_funcs"]
    base_funcs    = max(features["total_funcs"], 1)
    base_endpoints = features["total_endpoints"]

    n = 30
    funcs_arr   = rng.integers(max(1, base_funcs // 3), base_funcs * 3 + 1, n).astype(float)
    cx_arr      = np.clip(rng.normal(base_cx, 1.5, n), 1, 20)
    issues_arr  = np.clip(rng.integers(0, max(base_issues * 3 + 1, 5), n).astype(float), 0, None)
    tests_arr   = np.clip(rng.integers(0, max(base_tests * 3 + 1, 5), n).astype(float), 0, None)
    ep_arr      = np.clip(rng.integers(0, max(base_endpoints * 2 + 1, 3), n).astype(float), 0, None)

    noise       = rng.normal(0, 4, n)
    y_arr       = np.clip(
        base_quality
        - (cx_arr - base_cx) * 3
        - issues_arr * 1.5
        + tests_arr * 2
        + ep_arr * 0.5
        + noise,
        0, 100
    )

    X = np.column_stack([funcs_arr, cx_arr, issues_arr, tests_arr, ep_arr])
    y = y_arr

    model = LinearRegression()
    model.fit(X, y)

    y_pred = model.predict(X)
    mae    = round(mean_absolute_error(y, y_pred), 2)
    r2     = round(model.score(X, y), 4)

    feature_names = ["Funciones", "Complejidad promedio", "Issues", "Tests", "Endpoints"]
    coefs = {name: round(float(c), 4) for name, c in zip(feature_names, model.coef_)}

    x_actual = np.array([[
        base_funcs, base_cx, base_issues, base_tests, base_endpoints
    ]])
    pred_actual = round(float(model.predict(x_actual)[0]), 2)

    # Top 5 puntos para mostrar en tabla
    sample_rows = []
    for i in range(min(10, n)):
        sample_rows.append({
            "funcs":      int(funcs_arr[i]),
            "complejidad": round(float(cx_arr[i]), 2),
            "issues":     int(issues_arr[i]),
            "tests":      int(tests_arr[i]),
            "endpoints":  int(ep_arr[i]),
            "y_real":     round(float(y_arr[i]), 2),
            "y_pred":     round(float(y_pred[i]), 2),
        })

    mayor_impacto = max(coefs, key=lambda k: abs(coefs[k]))

    return {
        "tipo": "Regresión Lineal Múltiple",
        "variables_x": feature_names,
        "variable_y":  "Quality Score (0-100)",
        "coeficientes": coefs,
        "intercepto":  round(float(model.intercept_), 4),
        "r2":          r2,
        "mae":         mae,
        "prediccion_proyecto_actual": pred_actual,
        "muestra_datos": sample_rows,
        "interpretacion": (
            f"La variable con mayor impacto es '{mayor_impacto}' "
            f"(coef={coefs[mayor_impacto]}). "
            f"R²={r2} — el modelo explica el {round(r2 * 100, 1)}% de la variación. "
            f"Predicción para este proyecto: {pred_actual}/100 puntos."
        ),
    }


# ─── Regresión logística ──────────────────────────────────────────────────────

def logistic_regression(features: dict) -> dict:
    """
    Regresión logística:
      Clasifica cada función del proyecto como 'documentada' (1) o 'sin documentar' (0)
      basándose en su complejidad y si es async.

    Retorna probabilidades, métricas y la matriz de confusión.
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        mean_absolute_error, confusion_matrix, accuracy_score,
        precision_score, recall_score, f1_score
    )

    rng = np.random.default_rng(seed=99)

    doc_ratio    = features["doc_ratio"]
    base_cx      = max(features["avg_complexity"], 1.0)
    n_funcs      = max(features["total_funcs"], 20)

    # Generamos instancias sintéticas de funciones
    n = max(n_funcs * 2, 50)
    complexity_arr = np.clip(rng.exponential(base_cx, n), 1, 20)
    is_async_arr   = rng.binomial(1, features["async_funcs"] / max(n_funcs, 1), n).astype(float)
    params_arr     = np.clip(rng.integers(0, 8, n).astype(float), 0, None)

    # Mayor complejidad → menos probable que esté documentada
    prob_doc = np.clip(doc_ratio - (complexity_arr - base_cx) * 0.05 + is_async_arr * 0.05, 0.05, 0.95)
    y = rng.binomial(1, prob_doc)

    X = np.column_stack([complexity_arr, is_async_arr, params_arr])

    model = LogisticRegression(max_iter=500, random_state=42)
    model.fit(X, y)

    y_pred = model.predict(X)
    proba  = model.predict_proba(X)[:, 1]

    cm           = confusion_matrix(y, y_pred).tolist()
    accuracy     = round(accuracy_score(y, y_pred), 4)
    precision    = round(precision_score(y, y_pred, zero_division=0), 4)
    recall       = round(recall_score(y, y_pred, zero_division=0), 4)
    f1           = round(f1_score(y, y_pred, zero_division=0), 4)
    mae          = round(mean_absolute_error(y, y_pred), 4)

    # Predicción para el proyecto actual
    actual_x     = np.array([[base_cx, float(features["async_funcs"] > 0), 2.0]])
    prob_actual  = round(float(model.predict_proba(actual_x)[0][1]), 4)

    tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]

    return {
        "tipo": "Regresión Logística",
        "clases": ["Sin documentar (0)", "Documentada (1)"],
        "accuracy":   accuracy,
        "precision":  precision,
        "recall":     recall,
        "f1_score":   f1,
        "mae":        mae,
        "prob_documentada_actual": prob_actual,
        "matriz_confusion": {
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "raw": cm
        },
        "interpretacion": (
            f"El modelo predice con {round(accuracy * 100, 1)}% de exactitud si una función "
            f"está documentada. Para las funciones de este proyecto, la probabilidad promedio "
            f"de estar documentada es {round(prob_actual * 100, 1)}%. "
            f"F1-Score: {f1} (balance entre precisión y recall)."
        ),
    }


# ─── Error Absoluto (MAE) ─────────────────────────────────────────────────────

def mean_absolute_error_analysis(features: dict) -> dict:
    """
    Calcula el Error Absoluto Medio (MAE) entre:
      - quality_score real del proyecto
      - predicciones de los 3 modelos

    También muestra el MAE de cada modelo individualmente.
    """
    lr_simple   = linear_regression_simple(features)
    lr_multiple = linear_regression_multiple(features)
    lr_logistic = logistic_regression(features)

    real_quality = features["quality_score"]

    resultados = []

    if "prediccion_proyecto_actual" in lr_simple:
        pred = lr_simple["prediccion_proyecto_actual"]
        resultados.append({
            "modelo":     "Regresión Lineal Simple",
            "prediccion": pred,
            "mae_interno": lr_simple.get("mae", "-"),
            "error_abs_vs_real": round(abs(pred - real_quality), 2),
        })

    if "prediccion_proyecto_actual" in lr_multiple:
        pred = lr_multiple["prediccion_proyecto_actual"]
        resultados.append({
            "modelo":     "Regresión Lineal Múltiple",
            "prediccion": pred,
            "mae_interno": lr_multiple.get("mae", "-"),
            "error_abs_vs_real": round(abs(pred - real_quality), 2),
        })

    if "prob_documentada_actual" in lr_logistic:
        pred_pct = round(lr_logistic["prob_documentada_actual"] * 100, 2)
        resultados.append({
            "modelo":     "Regresión Logística",
            "prediccion": f"{pred_pct}% prob. documentada",
            "mae_interno": lr_logistic.get("mae", "-"),
            "error_abs_vs_real": "-",
        })

    mae_promedio = round(
        np.mean([r["error_abs_vs_real"] for r in resultados if isinstance(r["error_abs_vs_real"], float)]),
        2
    ) if resultados else 0

    return {
        "tipo": "Análisis de Error Absoluto Medio (MAE)",
        "quality_score_real": real_quality,
        "modelos": resultados,
        "mae_promedio_regresion": mae_promedio,
        "interpretacion": (
            f"El quality score real del proyecto es {real_quality}/100. "
            f"El MAE promedio entre los modelos de regresión y el valor real es {mae_promedio} puntos. "
            f"Un MAE bajo indica que los modelos predicen correctamente la calidad del proyecto."
        ),
    }


# ─── Función principal ────────────────────────────────────────────────────────

def run_ml_analysis(results: dict) -> dict:
    """
    Punto de entrada principal.
    Recibe el dict de ProjectAnalyzer.analyze() y devuelve todas las predicciones.

    Uso en routes/analysis.py:
        from services.ml_analyzer import run_ml_analysis
        ml_results = run_ml_analysis(analyzer_results)
    """
    features = _extract_features(results)

    return {
        "features":           features,
        "regresion_simple":   linear_regression_simple(features),
        "regresion_multiple": linear_regression_multiple(features),
        "regresion_logistica": logistic_regression(features),
        "mae_analysis":       mean_absolute_error_analysis(features),
    }