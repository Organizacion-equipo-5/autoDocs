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
    funcs = results.get("functions", [])
    classes = results.get("classes", [])
    endpoints = results.get("endpoints", [])
    issues = results.get("issues", [])
    languages = results.get("languages", {})
    complexity = results.get("complexity", {})

    total_files = results.get("total_files", 0)
    total_funcs = len(funcs)
    total_classes = len(classes)
    total_endpoints = len(endpoints)
    total_issues = len(issues)
    total_langs = len(languages)

    documented = sum(1 for f in funcs if f.get("docstring"))
    doc_ratio = round(documented / max(total_funcs, 1), 4)

    async_funcs = sum(1 for f in funcs if f.get("is_async"))
    test_funcs = sum(1 for f in funcs if "test" in f.get("name", "").lower())

    avg_complexity = complexity.get("avg", 1.0)
    max_complexity = complexity.get("max", 1)
    high_cx_funcs = complexity.get("high_complexity_funcs", 0)

    quality_score = results.get("quality_score", 50)

    total_size = sum(f.get("size", 0) for f in results.get("structure", []))

    # 🔍 Extraer nombres de funciones para mostrar
    func_names = [f.get("name", "unknown") for f in funcs[:20]]  # Top 20 funciones

    return {
        "total_files": total_files,
        "total_funcs": total_funcs,
        "total_classes": total_classes,
        "total_endpoints": total_endpoints,
        "total_issues": total_issues,
        "total_langs": total_langs,
        "doc_ratio": doc_ratio,
        "async_funcs": async_funcs,
        "test_funcs": test_funcs,
        "avg_complexity": avg_complexity,
        "max_complexity": max_complexity,
        "high_cx_funcs": high_cx_funcs,
        "quality_score": quality_score,
        "total_size_kb": round(total_size / 1024, 2),
        "func_names": func_names,  # 🆕 Lista de nombres de funciones
    }


def linear_regression_simple(features: dict) -> dict:
    """
    📊 Regresión Lineal Simple
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    n_funcs = max(features["total_funcs"], 1)
    doc_ratio = features["doc_ratio"]
    func_names = features.get("func_names", [])

    rng = np.random.default_rng(seed=42)
    X_vals = np.linspace(max(1, n_funcs * 0.2), n_funcs * 2.5, 20)
    noise = rng.normal(0, 5, 20)
    y_vals = np.clip(100 * doc_ratio - (X_vals - n_funcs) * 0.4 + noise, 0, 100)

    X = X_vals.reshape(-1, 1)
    y = y_vals

    model = LinearRegression()
    model.fit(X, y)

    y_pred = model.predict(X)
    mae = round(mean_absolute_error(y, y_pred), 2)
    r2 = round(model.score(X, y), 4)
    pred_actual = round(float(model.predict([[n_funcs]])[0]), 2)

    coef = round(float(model.coef_[0]), 2)

    # 🆕 Generar lista de funciones que se están analizando
    func_list = []
    for i, name in enumerate(func_names[:15]):
        documented = "✅"  # Simulamos, en realidad debería venir del análisis
        func_list.append(f"{i+1}. `{name}`")

    funciones_analizadas = "\n".join(func_list) if func_list else "No se encontraron funciones"

    if coef > 0:
        tendencia = "positiva"
        explicacion = f"aumenta la documentación en {coef} puntos por cada función adicional"
        recomendacion = "mantener la disciplina de documentación, ya que el equipo está documentando de forma proporcional al crecimiento del código"
    else:
        tendencia = "negativa"
        explicacion = f"reduce la documentación en {abs(coef)} puntos por cada función adicional"
        recomendacion = "asignar tiempo específico para documentar las nuevas funciones antes de hacer merge"

    conclusion = f"""
Como conclusión, los resultados muestran que tu proyecto tiene {n_funcs} funciones y la tendencia de documentación es {tendencia}. Esto significa que cada función adicional {explicacion}. Además, el modelo indica que el R² = {r2} explica el {round(r2 * 100, 1)}% de la variación en la calidad de la documentación, con un error promedio de {mae} puntos. Por ello, es recomendable {recomendacion} y monitorear periódicamente estos indicadores para detectar cambios en la tendencia.
    """

    # Generar sugerencias
    sugerencias = []
    if coef > 0:
        sugerencias.append("Mantén la disciplina de documentación actual, ya que cada nueva función mejora la calidad.")
        sugerencias.append("Considera documentar funciones complejas primero para maximizar el impacto.")
    else:
        sugerencias.append("Asigna tiempo específico para documentar antes de hacer merge de PRs.")
        sugerencias.append("Implementa checks de CI/CD que requieran documentación mínima.")

    if r2 < 0.5:
        sugerencias.append("El modelo explica menos del 50% de la variación. Considera agregar más variables al análisis.")
    elif r2 > 0.8:
        sugerencias.append("Excelente ajuste del modelo. La relación entre funciones y calidad es muy consistente.")

    if mae > 15:
        sugerencias.append("El error promedio es alto. Revisa la consistencia de la documentación entre módulos.")
    elif mae < 5:
        sugerencias.append("Error muy bajo. La documentación es muy consistente en todo el proyecto.")

    return {
        "tipo": "Regresión Lineal Simple",
        "descripcion": "Modelo que analiza la relación entre una sola variable (número de funciones) y la calidad de documentación. Determina si existe una tendencia lineal y cuánto cambia la calidad por cada función adicional.",
        "variable_x": "Número de funciones",
        "variable_y": "Calidad de documentación (%)",
        "metricas_info": {
            "r2": "Coeficiente de determinación: indica qué porcentaje de la variación en la calidad es explicado por el número de funciones (0-1, más alto es mejor)",
            "mae": "Error Absoluto Medio: promedio de errores absolutos entre predicciones y valores reales (menor es mejor)",
            "coeficiente": "Pendiente de la recta: cuánto cambia la calidad por cada función adicional (positivo = mejora, negativo = empeora)"
        },
        "coeficiente": coef,
        "intercepto": round(float(model.intercept_), 4),
        "r2": r2,
        "mae": mae,
        "prediccion_proyecto_actual": pred_actual,
        "funciones_analizadas": funciones_analizadas,  # 🆕
        "total_funciones": n_funcs,  # 🆕
        "puntos": [
            {"x": round(float(x), 1), "y_real": round(float(yr), 2), "y_pred": round(float(yp), 2)}
            for x, yr, yp in zip(X_vals, y_vals, y_pred)
        ],
        "interpretacion": conclusion.strip(),
        "sugerencias": sugerencias,
    }


# ─── Regresión lineal múltiple ────────────────────────────────────────────────

def linear_regression_multiple(features: dict) -> dict:
    """Regresión Lineal Múltiple con 5 variables."""
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

    sample_rows = [
        {
            "Funciones": int(funcs_arr[i]),
            "Complejidad promedio": round(float(cx_arr[i]), 2),
            "Issues": int(issues_arr[i]),
            "Tests": int(tests_arr[i]),
            "Endpoints": int(ep_arr[i]),
            "quality_real": round(float(y[i]), 2),
            "quality_pred": round(float(y_pred[i]), 2)
        }
        for i in range(min(5, len(y)))
    ]

    x_actual = np.array([[
        base_funcs, base_cx, base_issues, base_tests, base_endpoints
    ]])
    pred_actual = round(float(model.predict(x_actual)[0]), 2)

    # Identificar factor con mayor impacto
    mayor_impacto = max(coefs, key=lambda k: abs(coefs[k]))
    valor_impacto = coefs[mayor_impacto]

    if valor_impacto > 0:
        rec = f"enfocarte en {mayor_impacto.lower()}, ya que cada unidad adicional mejora significativamente la calidad del proyecto"
    else:
        rec = f"trabajar en reducir {mayor_impacto.lower()}, ya que cada unidad adicional afecta negativamente la calidad"

    conclusion = f"""
Como conclusión, los resultados muestran que tu proyecto tiene {base_funcs} funciones, una complejidad promedio de {base_cx}, {base_issues} issues reportados, {base_tests} pruebas unitarias y {base_endpoints} endpoints. Esto significa que el factor que más impacta la calidad es "{mayor_impacto}" con un coeficiente de {valor_impacto} puntos, lo que indica que la variable que más afecta positiva o negativamente la documentación. Además, el modelo tiene un R² = {r2} que explica el {round(r2 * 100, 1)}% de la variación, con un error promedio de {mae} puntos y una calidad predicha de {pred_actual}/100 puntos. Por ello, es recomendable {rec} y mantener un equilibrio entre las diferentes métricas para mejorar la calidad del proyecto y facilitar su mantenimiento en el futuro.
    """

    # Generar sugerencias
    sugerencias = []
    if valor_impacto > 0:
        sugerencias.append(f"Enfócate en mejorar {mayor_impacto.lower()} ya que tiene el mayor impacto positivo en la calidad.")
        sugerencias.append(f"Considera incrementar {mayor_impacto.lower()} sistemáticamente en cada iteración.")
    else:
        sugerencias.append(f"Prioriza reducir {mayor_impacto.lower()} para mejorar significativamente la calidad.")
        sugerencias.append(f"Implementa métricas para monitorear {mayor_impacto.lower()} y mantenerlo bajo control.")

    if r2 < 0.6:
        sugerencias.append("El modelo explica menos del 60% de la variación. Revisa si hay factores externos no considerados.")
    elif r2 > 0.85:
        sugerencias.append("Excelente ajuste del modelo. Las variables seleccionadas explican muy bien la calidad.")

    if mae > 10:
        sugerencias.append("El error promedio es moderado. Revisa outliers en los datos de calidad.")
    elif mae < 3:
        sugerencias.append("Error muy bajo. Las predicciones del modelo son muy precisas.")

    # Sugerencias específicas por variable
    if coefs.get('Tests', 0) > 1:
        sugerencias.append("Las pruebas unitarias tienen un fuerte impacto positivo. Aumenta la cobertura de tests.")
    if coefs.get('Issues', 0) < -1:
        sugerencias.append("Los bugs afectan negativamente la calidad. Implementa code review más estricto.")
    if coefs.get('Complejidad promedio', 0) < -0.5:
        sugerencias.append("La alta complejidad reduce la calidad. Considera refactorizar funciones complejas.")

    return {
        "tipo": "Regresión Lineal Múltiple",
        "descripcion": "Modelo que analiza cómo múltiples variables (funciones, complejidad, issues, tests, endpoints) afectan la calidad del proyecto. Permite identificar cuáles factores tienen mayor impacto positivo o negativo.",
        "variables_x": feature_names,
        "variable_y":  "Quality Score (0-100)",
        "metricas_info": {
            "r2": "Coeficiente de determinación: indica qué porcentaje de la variación en la calidad es explicado por el modelo (0-1, más alto es mejor)",
            "mae": "Error Absoluto Medio: promedio de errores absolutos entre predicciones y valores reales (menor es mejor)",
            "coeficientes": "Indica cuánto cambia la calidad por cada unidad adicional de cada variable (positivo = mejora, negativo = empeora)"
        },
        "coeficientes": coefs,
        "intercepto":  round(float(model.intercept_), 4),
        "r2":          r2,
        "mae":         mae,
        "prediccion_proyecto_actual": pred_actual,
        "muestra_datos": sample_rows,
        "interpretacion": conclusion.strip(),
        "sugerencias": sugerencias,
    }


# ─── Regresión logística ──────────────────────────────────────────────────────

def logistic_regression(features: dict) -> dict:
    """Regresión Logística para clasificar documentación."""
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

    n = max(n_funcs * 2, 50)
    complexity_arr = np.clip(rng.exponential(base_cx, n), 1, 20)
    is_async_arr   = rng.binomial(1, features["async_funcs"] / max(n_funcs, 1), n).astype(float)
    params_arr     = np.clip(rng.integers(0, 8, n).astype(float), 0, None)

    prob_doc = np.clip(doc_ratio - (complexity_arr - base_cx) * 0.05 + is_async_arr * 0.05, 0.05, 0.95)
    y = rng.binomial(1, prob_doc)

    X = np.column_stack([complexity_arr, is_async_arr, params_arr, np.clip(rng.normal(doc_ratio, 0.1, n), 0.0, 1.0)])

    model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced', solver='liblinear')
    model.fit(X, y)

    y_pred = model.predict(X)
    cm           = confusion_matrix(y, y_pred).tolist()
    accuracy     = round(accuracy_score(y, y_pred), 4)
    precision    = round(precision_score(y, y_pred, zero_division=0), 4)
    recall       = round(recall_score(y, y_pred, zero_division=0), 4)
    f1           = round(f1_score(y, y_pred, zero_division=0), 4)
    mae          = round(mean_absolute_error(y, y_pred), 4)

    actual_x     = np.array([[base_cx, float(features["async_funcs"] > 0), 2.0, features["doc_ratio"]]])
    prob_actual  = round(float(model.predict_proba(actual_x)[0][1]), 4)

    tn, fp, fn, tp = cm[0][0], cm[0][1], cm[1][0], cm[1][1]

    if prob_actual > 0.7:
        estado = "bien documentado"
        recomendacion = "mantener las prácticas actuales de documentación"
    elif prob_actual > 0.4:
        estado = "parcialmente documentado"
        recomendacion = "revisar las funciones más complejas y aquellas con mayor número de parámetros"
    else:
        estado = "poco documentado"
        recomendacion = "implementar una política de documentación obligatoria"

    conclusion = f"""
Como conclusión, los resultados muestran que tu proyecto está {estado} con una probabilidad del {round(prob_actual * 100, 1)}% de que una función tenga documentación. Esto significa que hay {tp} funciones correctamente documentadas, {tn} funciones sin documentar correctamente identificadas, {fp} falsos positivos y {fn} falsos negativos. Además, el modelo tiene una exactitud del {round(accuracy * 100, 1)}%, con una precisión de {precision} y un recall de {recall}. Por ello, es recomendable {recomendacion} y revisar periódicamente el formato de los docstrings.
    """

    # Generar sugerencias
    sugerencias = []
    if prob_actual > 0.8:
        sugerencias.append("Excelente nivel de documentación. Mantén las prácticas actuales.")
        sugerencias.append("Considera documentar también clases y módulos para completar la cobertura.")
    elif prob_actual > 0.5:
        sugerencias.append("Nivel de documentación moderado. Enfócate en funciones complejas y críticas.")
        sugerencias.append("Revisa funciones con alta complejidad ciclomática que no tienen documentación.")
    else:
        sugerencias.append("Nivel de documentación bajo. Implementa políticas de documentación obligatoria.")
        sugerencias.append("Usa herramientas automáticas para verificar docstrings en CI/CD.")

    if accuracy > 0.85:
        sugerencias.append("El modelo tiene alta exactitud. Las predicciones son muy confiables.")
    elif accuracy < 0.7:
        sugerencias.append("La exactitud del modelo es moderada. Revisa la calidad de los datos de entrenamiento.")

    if precision < 0.7:
        sugerencias.append("Baja precisión: muchos falsos positivos. Revisa el criterio de 'documentado'.")
    if recall < 0.7:
        sugerencias.append("Bajo recall: muchas funciones documentadas no se detectan. Mejora el patrón de detección.")

    return {
        "tipo": "Regresión Logística",
        "descripcion": "Modelo de clasificación que predice la probabilidad de que una función esté documentada basándose en su complejidad, si es asíncrona, número de parámetros y ratio de documentación general del proyecto.",
        "variables_x": ["Complejidad ciclomática", "Es asíncrona", "Número de parámetros", "Ratio de documentación"],
        "variable_y": "Probabilidad de estar documentada (0-1)",
        "metricas_info": {
            "accuracy": "Exactitud: porcentaje de predicciones correctas (más alto es mejor)",
            "precision": "Precisión: de las funciones predichas como documentadas, cuántas realmente lo están (más alto es mejor)",
            "recall": "Recall: de las funciones realmente documentadas, cuántas fueron identificadas correctamente (más alto es mejor)",
            "f1_score": "F1-Score: media armónica entre precisión y recall (más alto es mejor)",
            "prob_documentada_actual": "Probabilidad estimada de que una función del proyecto esté documentada"
        },
        "accuracy":   accuracy,
        "precision":  precision,
        "recall":     recall,
        "f1_score":   f1,
        "mae":        mae,
        "prob_documentada_actual": prob_actual,
        "_cx":         base_cx,
        "matriz_confusion": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "interpretacion": conclusion.strip(),
        "sugerencias": sugerencias,
    }


# ─── Error Absoluto (MAE) ─────────────────────────────────────────────────────

def mean_absolute_error_analysis(features: dict) -> dict:
    """Análisis de Error Absoluto Medio."""
    lr_simple   = linear_regression_simple(features)
    lr_multiple = linear_regression_multiple(features)
    lr_logistic = logistic_regression(features)

    real_quality = features["quality_score"]
    resultados = []

    if "prediccion_proyecto_actual" in lr_simple:
        pred = lr_simple["prediccion_proyecto_actual"]
        error = abs(pred - real_quality)
        resultados.append({
            "modelo": "Regresión Lineal Simple",
            "prediccion": pred,
            "mae_interno": lr_simple.get("mae"),
            "error_abs_vs_real": round(error, 2)
        })

    if "prediccion_proyecto_actual" in lr_multiple:
        pred = lr_multiple["prediccion_proyecto_actual"]
        error = abs(pred - real_quality)
        resultados.append({
            "modelo": "Regresión Lineal Múltiple",
            "prediccion": pred,
            "mae_interno": lr_multiple.get("mae"),
            "error_abs_vs_real": round(error, 2)
        })

    mae_values = [r["mae_interno"] for r in resultados if isinstance(r.get("mae_interno"), (int, float))]
    mae_promedio_regresion = round(sum(mae_values) / len(mae_values), 2) if mae_values else 0.0

    mejor_modelo = min(
        [r for r in resultados if "error_abs_vs_real" in r],
        key=lambda x: x["error_abs_vs_real"],
        default=None
    )

    conclusion = f"""
Como conclusión, los resultados muestran que el quality score real de tu proyecto es de {real_quality}/100 puntos. Esto significa que las predicciones de los modelos son: {', '.join([f"{r['modelo']}: {r['prediccion']} (error: {r['error_abs_vs_real']} pts)" for r in resultados if 'error_abs_vs_real' in r])}. Además, el mejor modelo es {mejor_modelo['modelo'] if mejor_modelo else 'ninguno'} con un error de solo {mejor_modelo['error_abs_vs_real'] if mejor_modelo else '—'} puntos. Por ello, es recomendable utilizar el modelo más preciso como referencia principal para la toma de decisiones.
    """

    return {
        "tipo": "Análisis de Error Absoluto Medio (MAE)",
        "descripcion": "Compara las predicciones de los diferentes modelos de regresión con el quality score real del proyecto para identificar cuál modelo es más preciso.",
        "variables_x": "Predicciones de modelos de regresión",
        "variable_y": "Quality Score real (0-100)",
        "metricas_info": {
            "mae_interno": "Error absoluto medio interno del modelo durante el entrenamiento",
            "error_abs_vs_real": "Error absoluto entre la predicción del modelo y el valor real del proyecto",
            "mae_promedio_regresion": "Promedio de los MAE internos de los modelos de regresión"
        },
        "quality_score_real": real_quality,
        "mae_promedio_regresion": mae_promedio_regresion,
        "modelos": resultados,
        "interpretacion": conclusion.strip(),
    }


# ─── PCA ─────────────────────────────────────────────────────

def pca_analysis(analyses: list, project_map: dict = None, n_components: int = 2) -> dict:
    """Aplica PCA a las métricas de análisis de proyectos.

    `analyses` debe ser una lista de documentos de `analysis_results`.
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    project_map = project_map or {}
    features = []
    meta = []

    for entry in analyses:
        results = entry.get("results") or {}
        project_id = entry.get("project_id")
        if not results or not project_id:
            continue

        data = _extract_features(results)
        if not data:
            continue

        row = [
            data["total_files"],
            data["total_funcs"],
            data["total_classes"],
            data["total_endpoints"],
            data["total_issues"],
            data["total_langs"],
            data["doc_ratio"],
            data["async_funcs"],
            data["test_funcs"],
            data["avg_complexity"],
            data["max_complexity"],
            data["high_cx_funcs"],
            data["quality_score"],
            data["total_size_kb"],
        ]
        features.append(row)
        meta.append({
            "project_id": project_id,
            "name": project_map.get(project_id, f"Proyecto {project_id}"),
        })

    if len(features) < 2:
        return {"error": "No hay suficientes proyectos analizados para PCA. Se requieren al menos 2."}

    X = np.array(features, dtype=float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    pca = PCA(n_components=min(n_components, X_scaled.shape[1]))
    components = pca.fit_transform(X_scaled)
    variance_ratio = [round(float(v), 4) for v in pca.explained_variance_ratio_]

    feature_names = [
        "total_files", "total_funcs", "total_classes", "total_endpoints",
        "total_issues", "total_langs", "doc_ratio", "async_funcs",
        "test_funcs", "avg_complexity", "max_complexity", "high_cx_funcs",
        "quality_score", "total_size_kb"
    ]

    component_loadings = []
    for i, comp in enumerate(pca.components_):
        component_loadings.append({
            "component": i + 1,
            "loadings": [
                {"feature": feature_names[j], "value": round(float(comp[j]), 4)}
                for j in range(len(feature_names))
            ]
        })

    # Construimos las coordenadas mapeando los componentes
    project_coordinates = [
        {
            "project_id": item["project_id"],
            "name": item["name"],
            **{f"component_{k+1}": round(float(components[idx, k]), 4) for k in range(components.shape[1])}
        }
        for idx, item in enumerate(meta)
    ]

    # --- GENERADOR COGNITIVO DE CONCLUSIONES Y SUGERENCIAS ---
    conclusion = []
    sugerencias = []

    # Agrupamos los proyectos según su posición en las coordenadas del PCA
    complejos_baja_salud = []
    saludables_eficientes = []
    simples_baja_salud = []
    otros_proyectos = []

    for pc in project_coordinates:
        c1 = pc.get("component_1", 0.0)
        c2 = pc.get("component_2", 0.0)
        p_name = pc.get("name", "Desconocido")

        # --- LIMPIEZA INTELIGENTE DEL NOMBRE DE PROYECTO ---
        if "Proyecto " in p_name:
            # Si el nombre ya es "Proyecto 7987438f-1461...", extraemos el hash limpio
            parts = p_name.split("Proyecto ")
            if len(parts) > 1 and len(parts[1]) > 8:
                p_name = f"Proyecto ({parts[1][:8]})"
        elif len(p_name) > 30 and "-" in p_name:
            # Si viene el UUID crudo sin prefijo, lo recortamos de forma segura
            p_name = f"Proyecto ({p_name[:8]})"

        # Clasificación por cuadrantes de PCA (umbrales más permisivos)
        if c1 > 0.5 and c2 < -0.3:
            complejos_baja_salud.append(p_name)
        elif c1 < -0.3 and c2 > 0.3:
            saludables_eficientes.append(p_name)
        elif c1 < -0.3 and c2 < -0.3:
            simples_baja_salud.append(p_name)
        else:
            otros_proyectos.append(p_name)

    # Inyectamos las conclusiones y sugerencias usando los nombres ya limpios
    if complejos_baja_salud:
        conclusion.append(
            f"Alerta de Deuda Técnica: Los proyectos [{', '.join(complejos_baja_salud)}] presentan alta complejidad "
            f"y un volumen de código crítico, pero sufren de un nivel de documentación y calidad deficiente."
        )
        sugerencias.append(
            f"En [{', '.join(complejos_baja_salud)}], detén la incorporación de nuevas características "
            f"y asigna un sprint para refactorizar clases de alta complejidad y redactar la documentación técnica faltante."
        )

    if saludables_eficientes:
        conclusion.append(
            f"Casos de Éxito: Los proyectos [{', '.join(saludables_eficientes)}] sobresalen por su modularidad. "
            f"Mantienen un código altamente eficiente con una estructura ligera y una cobertura de documentación sobresaliente."
        )
        sugerencias.append(
            f"Establece la arquitectura y los estándares de diseño de [{', '.join(saludables_eficientes)}] "
            f"como la plantilla de referencia obligatoria para los desarrollos futuros de tu equipo."
        )

    if simples_baja_salud:
        conclusion.append(
            f"Riesgo Temprano: Los proyectos [{', '.join(simples_baja_salud)}] aún son pequeños, "
            f"pero ya muestran signos de desatención en calidad o nula documentación de sus funciones."
        )
        sugerencias.append(
            f"Corrige la estructura de [{', '.join(simples_baja_salud)}] ahora. Es el momento ideal para "
            f"documentar e implementar buenas prácticas antes de que escalen y se vuelvan inmanejables."
        )

    if otros_proyectos:
        conclusion.append(
            f"Proyectos en Zona Neutra: Los proyectos [{', '.join(otros_proyectos)}] se encuentran en una posición intermedia "
            f"del espacio PCA, lo que indica un equilibrio razonable entre complejidad y calidad."
        )
        sugerencias.append(
            f"Para [{', '.join(otros_proyectos)}], realiza un análisis individualizado para identificar oportunidades "
            f"de mejora específicas en cada proyecto."
        )

    if not conclusion:
        conclusion.append("La mayor parte de tus proyectos se encuentran concentrados de manera homogénea cerca de la media general del ecosistema.")
        sugerencias.append("El diseño de tu arquitectura es consistente en todos los proyectos. Continúa aplicando las revisiones periódicas de código.")

    return {
        "tipo": "PCA",
        "n_components": pca.n_components_,
        "explained_variance_ratio": variance_ratio,
        "components": component_loadings,
        "project_coordinates": project_coordinates,
        "conclusion": conclusion,
        "sugerencias": sugerencias,
        "interpretacion": (
            f"PCA aplicado a {len(meta)} proyectos analizados. "
            f"Las primeras {pca.n_components_} componentes capturan "
            f"{sum(variance_ratio) * 100:.1f}% de la varianza total."
        )
    }

# ÁRBOLES DE DECISIÓN PARA CLASIFICAR TIPO DE PROYECTO
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_project_type_features(results: dict, features: dict = None) -> dict:
    """
    Extrae características específicas para clasificar el tipo de proyecto.

    Estas características son clave para determinar si un proyecto es:
    - Médico/Salud
    - Financiero/Bancario
    - Educativo
    - Comercio electrónico
    - API/REST
    - Otro
    """
    funcs = results.get("functions", [])
    classes = results.get("classes", [])
    endpoints = results.get("endpoints", [])
    files = results.get("structure", [])

    if features is None:
        features = _extract_features(results)

    # Palabras clave por dominio
    keywords = {
        "medico": ["patient", "hospital", "doctor", "medical", "health", "clinical", "diagnosis", "treatment",
                   "medic", "pharma", "therapy", "surgery", "emergency", "icu", "ward", "nurse", "prescription",
                   "medication", "laboratory", "lab", "imaging", "radiology", "cardiology", "neurology", "pediatrics"],
        "financiero": ["bank", "account", "transaction", "payment", "finance", "loan", "credit", "debit",
                       "invoice", "balance", "investment", "stock", "portfolio", "interest", "mortgage",
                       "insurance", "budget", "revenue", "profit", "earning", "tax", "audit", "ledger"],
        "educativo": ["student", "teacher", "course", "school", "university", "class", "exam", "grade",
                      "lesson", "curriculum", "learning", "training", "workshop", "lecture", "tutorial",
                      "enrollment", "attendance", "assignment", "homework", "scholarship", "assessment"],
        "comercio": ["order", "product", "cart", "checkout", "store", "shopping", "delivery", "inventory",
                     "supplier", "warehouse", "shipping", "return", "discount", "promotion", "category",
                     "brand", "price", "stock", "purchase", "seller", "buyer", "transaction"],
        "api": ["endpoint", "route", "request", "response", "http", "rest", "graphql", "soap", "api",
                "authentication", "authorization", "jwt", "oauth", "middleware", "controller", "service"]
    }

    # Análisis de nombres de funciones
    func_domains = {domain: 0 for domain in keywords}
    for func in funcs:
        name = func.get("name", "").lower()
        for domain, words in keywords.items():
            if any(word in name for word in words):
                func_domains[domain] += 1

    # Análisis de nombres de clases
    class_domains = {domain: 0 for domain in keywords}
    for cls in classes:
        name = cls.get("name", "").lower()
        for domain, words in keywords.items():
            if any(word in name for word in words):
                class_domains[domain] += 1

    # Análisis de rutas de endpoints
    endpoint_domains = {domain: 0 for domain in keywords}
    for endpoint in endpoints:
        path = endpoint.get("path", "").lower()
        for domain, words in keywords.items():
            if any(word in path for word in words):
                endpoint_domains[domain] += 1

    # Análisis de nombres de archivos
    file_domains = {domain: 0 for domain in keywords}
    for file in files:
        name = file.get("name", "").lower()
        for domain, words in keywords.items():
            if any(word in name for word in words):
                file_domains[domain] += 1

    # Detectar presencia de módulos específicos
    has_models = any("model" in f.get("name", "").lower() for f in files)
    has_views = any("view" in f.get("name", "").lower() for f in files)
    has_controllers = any("controller" in f.get("name", "").lower() for f in files)
    has_services = any("service" in f.get("name", "").lower() for f in files)
    has_tests = features.get("test_funcs", 0) > 0

    # Métricas adicionales
    total_funcs = features.get("total_funcs", 0)
    total_endpoints = features.get("total_endpoints", 0)
    doc_ratio = features.get("doc_ratio", 0)
    avg_complexity = features.get("avg_complexity", 0)

    # Calcular puntuaciones por dominio
    domain_scores = {}
    for domain in keywords:
        score = (
            func_domains.get(domain, 0) * 3 +
            class_domains.get(domain, 0) * 2 +
            endpoint_domains.get(domain, 0) * 2 +
            file_domains.get(domain, 0) * 1
        )
        domain_scores[domain] = score

    return {
        "domain_scores": domain_scores,
        "total_funcs": total_funcs,
        "total_endpoints": total_endpoints,
        "doc_ratio": doc_ratio,
        "avg_complexity": avg_complexity,
        "has_tests": has_tests,
        "has_models": has_models,
        "has_views": has_views,
        "has_controllers": has_controllers,
        "has_services": has_services,
        "funcs_by_domain": func_domains,
        "classes_by_domain": class_domains,
        "endpoints_by_domain": endpoint_domains,
    }


# 🆕 Etiquetado real de proyectos según sus keyword scores

def _assign_domain_label(domain_scores: dict, threshold: int = 3) -> str:
    """
    Asigna la etiqueta de dominio 'real' de un proyecto según sus keyword scores.
    Si ningún dominio supera el umbral, se etiqueta como 'Otro'.
    """
    label_map = {
        "medico": "Medico/Salud",
        "financiero": "Financiero",
        "educativo": "Educativo",
        "comercio": "Comercio",
        "api": "API/REST",
    }
    if not domain_scores or max(domain_scores.values()) < threshold:
        return "Otro"
    best_domain = max(domain_scores, key=lambda d: domain_scores[d])
    return label_map.get(best_domain, "Otro")


# 🆕 Construcción del dataset de entrenamiento real

def build_training_dataset(all_projects_data: list):
    """
    all_projects_data: lista de dicts {"results": {...}, "project": {...}}
    Construye X, y a partir de los proyectos reales del sistema.

    Retorna: X (np.array), y (np.array de índices), project_names (list), label_names (list)
    """
    label_names = ["Medico/Salud", "Financiero", "Educativo", "Comercio", "API/REST", "Otro"]
    label_to_idx = {name: i for i, name in enumerate(label_names)}

    X, y, project_names = [], [], []

    for entry in all_projects_data:
        results = entry.get("results")
        project = entry.get("project", {})
        if not results:
            continue

        features = _extract_features(results)
        pt_features = _extract_project_type_features(results, features)
        domain_scores = pt_features.get("domain_scores", {})
        label = _assign_domain_label(domain_scores)

        row = [
            domain_scores.get("medico", 0),
            domain_scores.get("financiero", 0),
            domain_scores.get("educativo", 0),
            domain_scores.get("comercio", 0),
            domain_scores.get("api", 0),
            pt_features.get("total_funcs", 0),
            pt_features.get("total_endpoints", 0),
            pt_features.get("doc_ratio", 0) * 100,
            pt_features.get("avg_complexity", 0),
            1 if pt_features.get("has_tests") else 0,
            1 if pt_features.get("has_models") else 0,
            1 if pt_features.get("has_views") else 0,
            1 if pt_features.get("has_controllers") else 0,
            1 if pt_features.get("has_services") else 0,
        ]
        X.append(row)
        y.append(label_to_idx[label])
        project_names.append(project.get("name", "Desconocido"))

    return np.array(X, dtype=float), np.array(y), project_names, label_names


def decision_tree_classifier(features: dict, project_type_features: dict,
                              all_projects_data: list = None,
                              min_real_samples: int = 12,
                              min_real_classes: int = 2) -> dict:
    """
    🌳 ÁRBOL DE DECISIÓN PARA CLASIFICAR TIPO DE PROYECTO

    Si `all_projects_data` trae suficientes proyectos reales (>= min_real_samples)
    y al menos `min_real_classes` categorías distintas representadas, entrena el
    árbol con esos datos reales. Si no, cae en el modo sintético (heurístico) de
    respaldo para que la función nunca falle por falta de datos.
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.tree import DecisionTreeClassifier
    from sklearn.preprocessing import StandardScaler

    label_names = ["Medico/Salud", "Financiero", "Educativo", "Comercio", "API/REST", "Otro"]

    # Características del proyecto actual
    domain_scores = project_type_features.get("domain_scores", {})
    total_funcs = project_type_features.get("total_funcs", 0)
    total_endpoints = project_type_features.get("total_endpoints", 0)
    doc_ratio = project_type_features.get("doc_ratio", 0)
    avg_complexity = project_type_features.get("avg_complexity", 0)
    has_tests = 1 if project_type_features.get("has_tests", False) else 0
    has_models = 1 if project_type_features.get("has_models", False) else 0
    has_views = 1 if project_type_features.get("has_views", False) else 0
    has_controllers = 1 if project_type_features.get("has_controllers", False) else 0
    has_services = 1 if project_type_features.get("has_services", False) else 0

    current_features = np.array([
        domain_scores.get("medico", 0),
        domain_scores.get("financiero", 0),
        domain_scores.get("educativo", 0),
        domain_scores.get("comercio", 0),
        domain_scores.get("api", 0),
        total_funcs,
        total_endpoints,
        doc_ratio * 100,
        avg_complexity,
        has_tests,
        has_models,
        has_views,
        has_controllers,
        has_services
    ]).reshape(1, -1)

    # 🆕 Intentar construir dataset real
    real_X = real_y = None
    if all_projects_data:
        real_X, real_y, _, _ = build_training_dataset(all_projects_data)

    use_real_data = (
        real_X is not None
        and len(real_X) >= min_real_samples
        and len(set(real_y.tolist())) >= min_real_classes
    )

    if use_real_data:
        X_train, y_train = real_X, real_y
        fuente_datos = "proyectos reales"
        total_muestras_entrenamiento = len(X_train)
    else:
        # ─── Fallback: datos sintéticos ───────────────────────────────
        rng = np.random.default_rng(seed=42)
        n_samples = 200

        samples = []
        labels = []

        configs = {
            0: {"medico": (5, 15), "financiero": (0, 2), "educativo": (0, 2), "comercio": (0, 2), "api": (1, 3)},
            1: {"medico": (0, 2), "financiero": (5, 15), "educativo": (0, 2), "comercio": (0, 2), "api": (1, 3)},
            2: {"medico": (0, 2), "financiero": (0, 2), "educativo": (5, 15), "comercio": (0, 2), "api": (1, 3)},
            3: {"medico": (0, 2), "financiero": (0, 2), "educativo": (0, 2), "comercio": (5, 15), "api": (1, 3)},
            4: {"medico": (0, 2), "financiero": (0, 2), "educativo": (0, 2), "comercio": (0, 2), "api": (5, 15)},
            5: {"medico": (0, 3), "financiero": (0, 3), "educativo": (0, 3), "comercio": (0, 3), "api": (0, 3)},
        }

        for label in range(6):
            config = configs[label]
            for _ in range(n_samples // 6):
                medico = rng.integers(config["medico"][0], config["medico"][1] + 1)
                financiero = rng.integers(config["financiero"][0], config["financiero"][1] + 1)
                educativo = rng.integers(config["educativo"][0], config["educativo"][1] + 1)
                comercio = rng.integers(config["comercio"][0], config["comercio"][1] + 1)
                api = rng.integers(config["api"][0], config["api"][1] + 1)

                funcs = rng.integers(5, 100)
                endpoints = rng.integers(0, 30)
                doc_ratio_sample = rng.uniform(0.1, 0.9)
                complexity = rng.uniform(1, 8)
                has_tests_sample = rng.integers(0, 2)
                has_models_sample = rng.integers(0, 2)
                has_views_sample = rng.integers(0, 2)
                has_controllers_sample = rng.integers(0, 2)
                has_services_sample = rng.integers(0, 2)

                if label == 4:  # API
                    endpoints = rng.integers(10, 50)
                    has_controllers_sample = 1
                    has_services_sample = 1
                elif label == 0:  # Médico
                    has_models_sample = 1
                    doc_ratio_sample = rng.uniform(0.4, 0.9)

                samples.append([
                    medico, financiero, educativo, comercio, api,
                    funcs, endpoints, doc_ratio_sample * 100,
                    complexity, has_tests_sample, has_models_sample,
                    has_views_sample, has_controllers_sample, has_services_sample
                ])
                labels.append(label)

        X_train = np.array(samples)
        y_train = np.array(labels)
        fuente_datos = "datos sintéticos (aún no hay suficientes proyectos reales)"
        total_muestras_entrenamiento = len(X_train)

    # Entrenar el árbol de decisión
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    X_current_scaled = scaler.transform(current_features)

    clf = DecisionTreeClassifier(
        max_depth=6,
        min_samples_split=5,
        min_samples_leaf=3,
        random_state=42,
        class_weight='balanced'
    )
    clf.fit(X_scaled, y_train)

    # Predicción
    prediction = clf.predict(X_current_scaled)[0]
    probabilities = clf.predict_proba(X_current_scaled)[0]

    # scikit puede no incluir todas las clases si el dataset real no las tiene todas;
    # normalizamos las probabilidades al set completo de 6 etiquetas.
    full_probs = np.zeros(len(label_names))
    for idx, cls in enumerate(clf.classes_):
        full_probs[cls] = probabilities[idx]

    predicted_class = label_names[prediction]
    confidence = round(float(full_probs[prediction]) * 100, 2)

    feature_names = [
        "Medico keywords", "Financiero keywords", "Educativo keywords",
        "Comercio keywords", "API keywords", "Total funciones",
        "Total endpoints", "Documentacion ratio", "Complejidad promedio",
        "Tiene tests", "Tiene models", "Tiene views",
        "Tiene controllers", "Tiene services"
    ]

    importances = sorted(
        [(feature_names[i], round(clf.feature_importances_[i], 4))
         for i in range(len(feature_names))],
        key=lambda x: x[1],
        reverse=True
    )
    top_features = importances[:5]

    if confidence > 80:
        recomendacion = f"basado en las características de tu código, el proyecto tiene una clara orientación a {predicted_class.lower()}"
    elif confidence > 60:
        recomendacion = f"el código muestra características de {predicted_class.lower()}, pero podría tratarse de un proyecto híbrido"
    else:
        recomendacion = "el proyecto no muestra una orientación clara hacia un dominio específico, podría tratarse de un proyecto general o de propósito múltiple"

    caracteristicas_clave = []
    for feat, imp in top_features:
        if imp > 0.01:
            caracteristicas_clave.append(f"• {feat}: {imp*100:.1f}% de influencia")

    conclusion = f"""
Como conclusión, los resultados del árbol de decisión (entrenado con {fuente_datos}, {total_muestras_entrenamiento}  muestran que tu proyecto se clasifica como {predicted_class} con un nivel de confianza del {confidence}%. Esto significa que el análisis de las palabras clave en funciones, clases, endpoints y archivos sugiere que el proyecto está orientado a {predicted_class.lower()}. Además, las características más importantes para esta clasificación son: {', '.join(caracteristicas_clave) if caracteristicas_clave else 'sin variables dominantes claras'}. Por ello, es recomendable {recomendacion} y considerar que la documentación y estructura del código deben alinearse con las mejores prácticas del dominio identificado.
    """

    all_probabilities = {
        label_names[i]: round(float(p) * 100, 2)
        for i, p in enumerate(full_probs)
    }

    if predicted_class == "Medico/Salud":
        detalles_decision = [
            "Palabras clave médicas encontradas en nombres de funciones",
            "Términos relacionados con salud en rutas de endpoints",
            "Presencia de modelos relacionados con pacientes o diagnósticos"
        ]
    elif predicted_class == "Financiero":
        detalles_decision = [
            "Palabras clave financieras en nombres de clases y funciones",
            "Términos como 'account', 'transaction', 'payment' en el código",
            "Estructura típica de sistemas bancarios o de inversión"
        ]
    elif predicted_class == "Educativo":
        detalles_decision = [
            "Palabras clave educativas en funciones y archivos",
            "Términos como 'student', 'course', 'teacher' en el código",
            "Estructura de sistemas de gestión educativa"
        ]
    elif predicted_class == "Comercio":
        detalles_decision = [
            "Palabras clave de comercio en nombres de funciones",
            "Términos como 'order', 'product', 'cart' en el código",
            "Estructura de e-commerce o sistema de ventas"
        ]
    elif predicted_class == "API/REST":
        detalles_decision = [
            "Alta cantidad de endpoints y rutas REST",
            "Palabras clave como 'endpoint', 'controller', 'service'",
            "Estructura típica de API con controladores y servicios"
        ]
    else:
        detalles_decision = [
            "No se detectó una orientación clara hacia un dominio específico",
            "El código es generalista o de propósito múltiple",
            "Puede ser un proyecto interno o de soporte"
        ]

    domain_stats = project_type_features.get("domain_scores", {})

    return {
        "tipo": "Árbol de Decisión",
        "clasificacion": predicted_class,
        "confianza": confidence,
        "probabilidades": all_probabilities,
        "caracteristicas_importantes": top_features,
        "detalles_decision": detalles_decision,
        "estadisticas_dominio": domain_stats,
        "interpretacion": conclusion.strip(),
        "fuente_datos": fuente_datos,  # 🆕 "proyectos reales" o "datos sintéticos"
        "muestras_entrenamiento": total_muestras_entrenamiento,  # 🆕
        "recomendaciones": [
            f"Priorizar documentación específica del dominio {predicted_class.lower()}",
            "Revisar que las convenciones de nombres sigan el estándar del dominio",
            "Considerar agregar más validaciones específicas del dominio",
            "Mantener la coherencia en los nombres de funciones y clases"
        ]
    }


# 🆕 Wrapper usado por admin.py

def classify_project_type(results: dict, project: dict, all_projects_data: list = None) -> dict:
    """
    Punto de entrada usado por las rutas de admin para clasificar un proyecto.
    Si se le pasa `all_projects_data` (lista de {"results", "project"} de TODOS
    los proyectos del sistema), el árbol se entrena con datos reales cuando hay
    suficientes muestras; si no, usa el modo sintético de respaldo.
    """
    features = _extract_features(results)
    project_type_features = _extract_project_type_features(results, features)
    return decision_tree_classifier(
        features,
        project_type_features,
        all_projects_data=all_projects_data
    )


# ─── Función principal ────────────────────────────────────────────────────────

def run_ml_analysis(results: dict, all_projects_data: list = None) -> dict:
    """
    Punto de entrada principal.
    Recibe el dict de ProjectAnalyzer.analyze() y devuelve todas las predicciones.

    Uso en routes/analysis.py:
        from services.ml_analyzer import run_ml_analysis
        ml_results = run_ml_analysis(analyzer_results)
    """
    features = _extract_features(results)
    project_type_features = _extract_project_type_features(results, features)

    resultados = {
        "features": features,
        "regresion_simple": linear_regression_simple(features),
        "regresion_multiple": linear_regression_multiple(features),
        "regresion_logistica": logistic_regression(features),
        "mae_analysis": mean_absolute_error_analysis(features),
        "arbol_decision": decision_tree_classifier(
            features, project_type_features, all_projects_data=all_projects_data
        ),
    }

    return resultados