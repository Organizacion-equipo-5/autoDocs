"""
services/plan_recommender.py

Servicio 100% independiente para recomendar planes basado en uso real.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import numpy as np
import sys

# Número máximo de clusters (k) a evaluar
K_MAX = 5
# Mínimo de usuarios con actividad necesarios para agrupar
MIN_USERS_FOR_CLUSTERING = 6

FEATURE_NAMES = [
    "projects_count",
    "analyses_30d",
    "analyses_total",
    "ai_usage_count",
    "export_usage_count",
]


# ─── Helpers internos ────────────────────────────────────────────────────────

def _get_plans() -> dict:
    """
    Carga PLANS de payments.py sin crear import circular.
    """
    try:
        if "routes.payments" in sys.modules:
            from routes.payments import PLANS
            return PLANS
        from routes import payments
        return payments.PLANS
    except (ImportError, AttributeError):
        # Fallback: definición manual de planes
        return {
            "free": {
                "name": "Free",
                "price": 0,
                "projects_limit": 2,
                "analyses_per_month": 5,
                "export_pdf": False,
                "ai_enhanced": False,
            },
            "pro": {
                "name": "Pro",
                "price": 29,
                "projects_limit": 20,
                "analyses_per_month": 100,
                "export_pdf": True,
                "ai_enhanced": True,
            },
            "business": {
                "name": "Business",
                "price": 79,
                "projects_limit": 100,
                "analyses_per_month": 500,
                "export_pdf": True,
                "ai_enhanced": True,
            },
            "enterprise": {
                "name": "Enterprise",
                "price": 199,
                "projects_limit": -1,
                "analyses_per_month": -1,
                "export_pdf": True,
                "ai_enhanced": True,
            },
        }


def _safe_import() -> bool:
    """Intenta importar scikit-learn; retorna False si no está instalado."""
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def log_usage(db, user_id: str, action: str, metadata: Optional[dict] = None):
    """
    Helper para registrar uso real de IA y exportaciones en usage_logs.
    
    Args:
        db: instancia de MongoDB (de get_db())
        user_id: ID del usuario
        action: "ai_enhanced", "export_pdf", "export_html", "export_markdown"
        metadata: datos adicionales (opcional)
    
    Ejemplo:
        from services.plan_recommender import log_usage
        log_usage(db, user_id, "ai_enhanced", {"document_id": doc_id})
    """
    try:
        log_entry = {
            "user_id": user_id,
            "action": action,
            "created_at": datetime.utcnow().isoformat(),
        }
        if metadata:
            log_entry["metadata"] = metadata
        db.usage_logs.insert_one(log_entry)
        return True
    except Exception as e:
        print(f"⚠️ Error registrando uso: {e}")
        return False


def _extract_usage_features(db):
    """
    Construye la matriz de features usando la conexión a DB existente.
    """
    print(f"[DEBUG plan_recommender] _extract_usage_features called")
    
    # Obtener todos los usuarios
    users = list(db.users.find({}, {"_id": 1, "plan": 1}))
    print(f"[DEBUG plan_recommender] Found {len(users)} users")
    if not users:
        return [], np.empty((0, len(FEATURE_NAMES))), {}

    start_30d = (datetime.utcnow() - timedelta(days=30)).isoformat()
    
    user_ids = []
    rows = []
    raw_usage = {}

    for u in users:
        uid = u["_id"]
        print(f"[DEBUG plan_recommender] Processing user: {uid}")
        
        # 1. Proyectos del usuario (corregido: usar db.projects en lugar de db.documents)
        project_ids = [p["_id"] for p in db.projects.find({"user_id": uid}, {"_id": 1})]
        projects_count = len(project_ids)
        print(f"[DEBUG plan_recommender] User {uid} has {projects_count} projects")
        
        # 2. Análisis totales y en últimos 30 días (corregido: usar project_id en lugar de document_id)
        analyses_total = 0
        analyses_30d = 0
        if project_ids:
            analyses_total = db.analysis_results.count_documents({
                "project_id": {"$in": project_ids}
            })
            analyses_30d = db.analysis_results.count_documents({
                "project_id": {"$in": project_ids},
                "created_at": {"$gte": start_30d}
            })
        print(f"[DEBUG plan_recommender] User {uid} has {analyses_total} total analyses, {analyses_30d} in last 30 days")
        
        # 3. Uso de IA y exportaciones (desde usage_logs)
        ai_usage_count = 0
        export_usage_count = 0
        try:
            # Verificar si existe la colección usage_logs
            if "usage_logs" in db.list_collection_names():
                ai_usage_count = db.usage_logs.count_documents({
                    "user_id": uid,
                    "action": "ai_enhanced"
                })
                export_usage_count = db.usage_logs.count_documents({
                    "user_id": uid,
                    "action": {"$in": ["export_pdf", "export_html", "export_markdown"]}
                })
        except Exception:
            pass

        usage = {
            "projects_count": projects_count,
            "analyses_30d": analyses_30d,
            "analyses_total": analyses_total,
            "ai_usage_count": ai_usage_count,
            "export_usage_count": export_usage_count,
            "plan": u.get("plan", "free"),
        }

        raw_usage[uid] = usage
        user_ids.append(uid)
        rows.append([
            usage["projects_count"],
            usage["analyses_30d"],
            usage["analyses_total"],
            usage["ai_usage_count"],
            usage["export_usage_count"],
        ])

    X = np.array(rows, dtype=float)
    return user_ids, X, raw_usage


# ─── Método del codo (Elbow Method) ──────────────────────────────────────────

def elbow_method(X_scaled: np.ndarray, k_max: int = K_MAX) -> List[dict]:
    """Calcula la inercia para k = 1..k_max."""
    from sklearn.cluster import KMeans

    n_samples = X_scaled.shape[0]
    k_max = min(k_max, max(1, n_samples - 1))

    resultados = []
    for k in range(1, k_max + 1):
        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        model.fit(X_scaled)
        resultados.append({"k": k, "inertia": round(float(model.inertia_), 4)})
    return resultados


def _detectar_codo(elbow_data: List[dict]) -> int:
    """Detecta el 'codo' automáticamente."""
    if len(elbow_data) < 3:
        return elbow_data[-1]["k"] if elbow_data else 1

    ks = np.array([p["k"] for p in elbow_data], dtype=float)
    inertias = np.array([p["inertia"] for p in elbow_data], dtype=float)

    ks_n = (ks - ks.min()) / (ks.max() - ks.min() + 1e-9)
    in_n = (inertias - inertias.min()) / (inertias.max() - inertias.min() + 1e-9)

    p1 = np.array([ks_n[0], in_n[0]])
    p2 = np.array([ks_n[-1], in_n[-1]])
    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)

    distancias = []
    for x, y in zip(ks_n, in_n):
        p = np.array([x, y])
        if line_len == 0:
            distancias.append(0)
        else:
            distancias.append(float(np.abs(np.cross(line_vec, p - p1)) / line_len))

    idx_codo = int(np.argmax(distancias))
    return int(ks[idx_codo])


# ─── Coeficiente de Silueta (Silhouette Score) ───────────────────────────────

def silhouette_scores(X_scaled: np.ndarray, k_max: int = K_MAX) -> List[dict]:
    """Calcula el coeficiente de silueta para k = 2..k_max."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n_samples = X_scaled.shape[0]
    k_max = min(k_max, n_samples - 1)

    resultados = []
    for k in range(2, k_max + 1):
        model = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = model.fit_predict(X_scaled)
        try:
            score = silhouette_score(X_scaled, labels)
        except ValueError:
            continue
        resultados.append({"k": k, "score": round(float(score), 4)})
    return resultados


def _mejor_k(silhouette_data: List[dict], fallback_k: int) -> int:
    if not silhouette_data:
        return fallback_k
    mejor = max(silhouette_data, key=lambda x: x["score"])
    return mejor["k"]


def _describe_cluster(profile: dict, etiqueta: str = None) -> str:
    """
    Genera una descripción en lenguaje natural para un perfil de cluster.
    Usa umbrales simples para convertir promedios numéricos en texto.
    """
    if not profile:
        return etiqueta or "Grupo de uso"

    def _bucket_projects(n):
        if n <= 0: return 'sin proyectos'
        if n <= 3: return 'pocos proyectos'
        if n <= 10: return 'varios proyectos'
        return 'muchos proyectos'

    def _bucket_analyses(n):
        if n <= 0: return 'casi ningún análisis'
        if n <= 5: return 'análisis esporádicos'
        if n <= 20: return 'análisis frecuentes'
        return 'análisis intensivos'

    parts = []
    etiqueta_text = etiqueta or profile.get('etiqueta')
    if etiqueta_text:
        parts.append(f"{etiqueta_text}:")

    proj = profile.get('projects_count', 0)
    parts.append(f"Promedio de {proj} proyectos ({_bucket_projects(proj)})")

    anal = profile.get('analyses_30d', profile.get('analyses_total', 0))
    parts.append(f"~{anal} análisis en 30 días ({_bucket_analyses(anal)})")

    ai = profile.get('ai_usage_count', 0)
    parts.append("Usan IA" if ai > 0 else "No suelen usar IA")

    expo = profile.get('export_usage_count', 0)
    parts.append("Exportan con frecuencia" if expo > 0 else "Raras exportaciones")

    dbu = profile.get('db_usage_count', 0)
    parts.append("Incluyen uso de base de datos" if dbu > 0 else "Sin uso de base de datos")

    return ' · '.join(parts)

# ─── Clustering completo de usuarios ───────────────────────────────────────

def cluster_users(db, k_max: int = K_MAX) -> dict:
    """
    Pipeline completo de clustering.
    """
    if not _safe_import():
        return {"error": "scikit-learn no está instalado."}

    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    user_ids, X, raw_usage = _extract_usage_features(db)

    if len(user_ids) < MIN_USERS_FOR_CLUSTERING:
        return {
            "disponible": False,
            "razon": f"Se necesitan al menos {MIN_USERS_FOR_CLUSTERING} usuarios con actividad "
                     f"para agrupar por patrón de uso (hay {len(user_ids)}).",
            "raw_usage": raw_usage,
        }

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    elbow_data = elbow_method(X_scaled, k_max)
    codo_k = _detectar_codo(elbow_data)

    silhouette_data = silhouette_scores(X_scaled, k_max)
    mejor_k = _mejor_k(silhouette_data, fallback_k=codo_k)
    mejor_k = max(2, mejor_k)

    modelo_final = KMeans(n_clusters=mejor_k, n_init=10, random_state=42)
    labels = modelo_final.fit_predict(X_scaled)

    # Perfil promedio de cada cluster
    perfiles = {}
    for cluster_id in range(mejor_k):
        idxs = np.where(labels == cluster_id)[0]
        if len(idxs) == 0:
            continue
        promedio = X[idxs].mean(axis=0)
        perfiles[cluster_id] = {
            name: round(float(val), 2) for name, val in zip(FEATURE_NAMES, promedio)
        }
        perfiles[cluster_id]["intensidad_uso"] = round(float(np.linalg.norm(promedio)), 2)

    # Ordenar clusters por intensidad de uso
    orden = sorted(perfiles.keys(), key=lambda c: perfiles[c]["intensidad_uso"])
    etiquetas = ["Ocasional", "Regular", "Frecuente", "Intensivo", "Power User"]
    etiqueta_por_cluster = {c: etiquetas[min(i, len(etiquetas) - 1)] for i, c in enumerate(orden)}

    user_to_cluster = {uid: int(label) for uid, label in zip(user_ids, labels)}

    return {
        "disponible": True,
        "k_max_evaluado": min(k_max, len(user_ids) - 1),
        "elbow": elbow_data,
        "codo_detectado": codo_k,
        "silhouette": silhouette_data,
        "k_optimo": mejor_k,
        "silhouette_score_final": next(
            (s["score"] for s in silhouette_data if s["k"] == mejor_k), None
        ),
        "perfiles_cluster": {
            str(c): {**perfiles[c], "etiqueta": etiqueta_por_cluster[c]} for c in perfiles
        },
        "describe_cluster": _describe_cluster,
        "user_to_cluster": user_to_cluster,
        "etiqueta_por_cluster": {str(k): v for k, v in etiqueta_por_cluster.items()},
        "raw_usage": raw_usage,
        "feature_names": FEATURE_NAMES,
    }


# ─── Recomendación de plan ──────────────────────────────────────────────────

def _plan_cubre_uso(plan_key: str, plan: dict, usage: dict) -> bool:
    """True si un plan alcanza para el uso real del usuario."""
    limit_proj = plan.get("projects_limit", -1)
    limit_an = plan.get("analyses_per_month", -1)

    if limit_proj != -1 and usage["projects_count"] > limit_proj:
        return False
    if limit_an != -1 and usage["analyses_30d"] > limit_an:
        return False
    
    if usage["export_usage_count"] > 0 and not plan.get("export_pdf", False):
        return False
    if usage["ai_usage_count"] > 0 and not plan.get("ai_enhanced", False):
        return False
    
    return True


def _plan_ideal_por_uso(usage: dict) -> str:
    """Plan más barato que cubre el uso real."""
    PLANS = _get_plans()
    candidatos = sorted(PLANS.items(), key=lambda kv: kv[1]["price"])
    for plan_key, plan in candidatos:
        if _plan_cubre_uso(plan_key, plan, usage):
            return plan_key
    return candidatos[-1][0]


def recommend_plan_for_user(db, user_id: str) -> dict:
    """
    Punto de entrada principal para la recomendación.
    
    Args:
        db: instancia de MongoDB (de get_db())
        user_id: ID del usuario
    
    Returns:
        dict: Recomendación completa con plan actual, plan ideal, uso real, etc.
    """
    print(f"[DEBUG plan_recommender] recommend_plan_for_user called for user_id: {user_id}")
    PLANS = _get_plans()

    user = db.users.find_one({"_id": user_id})
    if not user:
        print(f"[DEBUG plan_recommender] User not found: {user_id}")
        return {"error": "Usuario no encontrado"}
    
    print(f"[DEBUG plan_recommender] User found: {user.get('name', 'N/A')}, plan: {user.get('plan', 'free')}")

    plan_actual_key = user.get("plan", "free")
    plan_actual = PLANS.get(plan_actual_key, PLANS["free"])

    _, _, raw_usage = _extract_usage_features(db)
    print(f"[DEBUG plan_recommender] raw_usage keys: {list(raw_usage.keys())}")
    usage = raw_usage.get(user_id)
    if usage is None:
        print(f"[DEBUG plan_recommender] No usage data found for user_id: {user_id}")
        usage = {
            "projects_count": 0,
            "analyses_30d": 0,
            "analyses_total": 0,
            "ai_usage_count": 0,
            "export_usage_count": 0,
            "plan": plan_actual_key,
        }
    else:
        print(f"[DEBUG plan_recommender] Usage data for user: {usage}")

    plan_ideal_key = _plan_ideal_por_uso(usage)
    plan_ideal = PLANS[plan_ideal_key]

    # Clustering
    cluster_info = cluster_users(db)
    perfil_usuario = None
    if cluster_info.get("disponible"):
        cluster_id = cluster_info["user_to_cluster"].get(user_id)
        if cluster_id is not None:
            perfil = cluster_info["perfiles_cluster"].get(str(cluster_id))
            perfil_usuario = {
                "cluster_id": cluster_id,
                "etiqueta": perfil["etiqueta"] if perfil else None,
                "uso_promedio_grupo": perfil,
            }

    # Determinar tipo de recomendación
    orden_precio = sorted(PLANS.items(), key=lambda kv: kv[1]["price"])
    orden_keys = [k for k, _ in orden_precio]
    
    if plan_actual_key not in orden_keys:
        orden_keys.append(plan_actual_key)
        orden_keys = sorted(orden_keys, key=lambda k: PLANS.get(k, {}).get("price", 999))
    if plan_ideal_key not in orden_keys:
        orden_keys.append(plan_ideal_key)
        orden_keys = sorted(orden_keys, key=lambda k: PLANS.get(k, {}).get("price", 999))
    
    idx_actual = orden_keys.index(plan_actual_key)
    idx_ideal = orden_keys.index(plan_ideal_key)

    ahorro_mensual = round(plan_actual["price"] - plan_ideal["price"], 2)

    if idx_ideal < idx_actual:
        tipo = "promocion_downgrade"
        precio_promo = round(plan_ideal["price"] * 0.8, 2)
        mensaje = (
            f"Estás pagando {plan_actual['name']} (${plan_actual['price']}/mes) pero tu uso "
            f"real corresponde al plan {plan_ideal['name']} (${plan_ideal['price']}/mes). "
            f"Te ofrecemos {plan_ideal['name']} con 20% de descuento por 3 meses: "
            f"${precio_promo}/mes."
        )
        promocion = {
            "plan_sugerido": plan_ideal_key,
            "precio_lista": plan_ideal["price"],
            "precio_promocional": precio_promo,
            "descuento_pct": 20,
            "duracion_meses": 3,
            "ahorro_mensual_vs_actual": ahorro_mensual,
        }
    elif idx_ideal > idx_actual:
        tipo = "upgrade_necesario"
        mensaje = (
            f"Tu uso ({usage['projects_count']} proyectos, {usage['analyses_30d']} análisis "
            f"este mes) ya supera los límites de tu plan {plan_actual['name']}. "
            f"Te recomendamos subir a {plan_ideal['name']} (${plan_ideal['price']}/mes) "
            f"para no quedarte sin capacidad."
        )
        promocion = None
    else:
        tipo = "plan_ajustado"
        mensaje = f"Tu plan actual ({plan_actual['name']}) ya está bien ajustado a tu uso real."
        promocion = None

    # Construir descripciones legibles por cada cluster
    cluster_perfiles = cluster_info.get('perfiles_cluster', {})
    etiqueta_map = cluster_info.get('etiqueta_por_cluster', {})
    descriptions = {}
    for k, perfil in cluster_perfiles.items():
        descriptions[k] = _describe_cluster(perfil, etiqueta_map.get(k))

    return {
        "user_id": user_id,
        "plan_actual": {"key": plan_actual_key, **plan_actual},
        "plan_ideal": {"key": plan_ideal_key, **plan_ideal},
        "uso_real": usage,
        "tipo_recomendacion": tipo,
        "mensaje": mensaje,
        "promocion": promocion,
        "perfil_uso": perfil_usuario,
        "clustering": {
            "disponible": cluster_info.get("disponible", False),
            "razon_no_disponible": cluster_info.get("razon"),
            "k_optimo": cluster_info.get("k_optimo"),
            "codo_detectado": cluster_info.get("codo_detectado"),
            "silhouette_score_final": cluster_info.get("silhouette_score_final"),
            "elbow": cluster_info.get("elbow", []),
            "silhouette": cluster_info.get("silhouette", []),
            "perfiles_cluster": cluster_info.get("perfiles_cluster", {}),
            "etiqueta_por_cluster": cluster_info.get("etiqueta_por_cluster", {}),
            "user_to_cluster": cluster_info.get("user_to_cluster", {}),
            "descriptions": descriptions,
        },
    }