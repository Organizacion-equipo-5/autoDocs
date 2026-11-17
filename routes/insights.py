"""
routes/insights.py

Endpoints de "inteligencia" sobre un proyecto ya analizado:

    GET  /api/insights/<project_id>/health           código muerto, duplicado y mapa de calor
    GET  /api/insights/<project_id>/history          snapshots y tendencia del score
    GET  /api/insights/<project_id>/compare          diff entre dos análisis (?from=&to=)
    POST /api/insights/<project_id>/chat             chat con la documentación (RAG)
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services import analysis_history
from services.ai_enhancer import AIEnhancer
from services.code_health import analyze_code_health
from services.db import get_db
from services.doc_chat import Index, answer_question, build_chunks
from services.plan_recommender import log_usage

insights_bp = Blueprint('insights', __name__)

CHAT_ACTION = "doc_chat"
CHAT_LIMIT_PER_HOUR = 30
_INDEX_CACHE = OrderedDict()   # (project_id, created_at) -> Index
_INDEX_CACHE_SIZE = 16


def _get_project(db, project_id, user_id):
    return db.projects.find_one({"_id": project_id, "user_id": user_id})


def _plan_allows_ai(db, user_id) -> bool:
    from routes.payments import PLANS
    user = db.users.find_one({"_id": user_id}) or {}
    return bool(PLANS.get(user.get('plan', 'free'), PLANS['free']).get('ai_enhanced'))


def _cached_index(project_id, stored):
    key = (project_id, stored.get("created_at"))
    index = _INDEX_CACHE.get(key)
    if index is None:
        index = Index(build_chunks(stored.get("results"), stored.get("documentation")))
        _INDEX_CACHE[key] = index
        while len(_INDEX_CACHE) > _INDEX_CACHE_SIZE:
            _INDEX_CACHE.popitem(last=False)
    else:
        _INDEX_CACHE.move_to_end(key)
    return index


@insights_bp.route('/<project_id>/health', methods=['GET'])
@jwt_required()
def get_health(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    if not _get_project(db, project_id, user_id):
        return jsonify({"error": "Project not found"}), 404

    stored = db.analysis_results.find_one({"project_id": project_id})
    if not stored or not stored.get("results"):
        return jsonify({"available": False, "reason": "El proyecto aún no tiene un análisis completado."}), 200

    results = stored["results"]
    health = results.get("code_health")
    if not health:
        # Análisis anteriores a esta función: se calcula al vuelo si el código sigue en disco.
        # OJO: Path("") equivale a Path("."), es decir, el directorio de la propia aplicación.
        # Solo se aceptan rutas explícitas del proyecto y siempre dentro de uploads/.
        project = _get_project(db, project_id, user_id)
        uploads = Path('uploads').resolve()
        candidate = uploads / str(project_id)
        options = [candidate / 'src', candidate]
        if project.get("file_path"):
            options.insert(0, Path(project["file_path"]))
        root = None
        for opt in options:
            try:
                resolved = opt.resolve()
            except OSError:
                continue
            if resolved.is_dir() and uploads in resolved.parents:
                root = resolved
                break
        if root is None:
            return jsonify({"available": False,
                            "reason": "Vuelve a analizar el proyecto para generar este reporte."}), 200
        try:
            health = analyze_code_health(root, results)
            db.analysis_results.update_one(
                {"project_id": project_id}, {"$set": {"results.code_health": health}})
        except Exception as e:
            return jsonify({"error": f"No se pudo calcular la salud del código: {e}"}), 500
    return jsonify({"available": True, "health": health,
                    "quality_score": results.get("quality_score", 0)}), 200


@insights_bp.route('/<project_id>/history', methods=['GET'])
@jwt_required()
def get_history(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    if not _get_project(db, project_id, user_id):
        return jsonify({"error": "Project not found"}), 404
    snapshots = analysis_history.list_snapshots(db, project_id)
    return jsonify({"snapshots": analysis_history.trend(snapshots), "count": len(snapshots)}), 200


@insights_bp.route('/<project_id>/activity', methods=['GET'])
@jwt_required()
def get_activity(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    if not _get_project(db, project_id, user_id):
        return jsonify({"error": "Project not found"}), 404

    activities = list(
        db.github_activity.find({"project_id": project_id})
        .sort("occurred_at", -1)
        .limit(100)
    )
    for activity in activities:
        activity["id"] = str(activity.pop("_id"))
    return jsonify({"activities": activities, "count": len(activities)}), 200


@insights_bp.route('/<project_id>/compare', methods=['GET'])
@jwt_required()
def compare(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    if not _get_project(db, project_id, user_id):
        return jsonify({"error": "Project not found"}), 404
    try:
        old, new = analysis_history.resolve_pair(
            db, project_id, request.args.get('from'), request.args.get('to'))
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"diff": analysis_history.diff_snapshots(old, new),
                    "from_id": old["_id"], "to_id": new["_id"]}), 200


@insights_bp.route('/<project_id>/chat', methods=['POST'])
@jwt_required()
def chat(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    if not _get_project(db, project_id, user_id):
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "La pregunta es obligatoria"}), 400

    stored = db.analysis_results.find_one({"project_id": project_id})
    if not stored or not stored.get("results"):
        return jsonify({"error": "El proyecto aún no tiene un análisis completado."}), 409

    # Límite por hora para no agotar la cuota de la IA
    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    recent = db.usage_logs.count_documents(
        {"user_id": user_id, "action": CHAT_ACTION, "created_at": {"$gte": since}})
    if recent >= CHAT_LIMIT_PER_HOUR:
        return jsonify({"error": f"Límite de {CHAT_LIMIT_PER_HOUR} preguntas por hora alcanzado."}), 429

    use_ai = _plan_allows_ai(db, user_id)
    try:
        reply = answer_question(
            question, stored["results"], stored.get("documentation"),
            history=data.get("history"), ai=AIEnhancer() if use_ai else None,
            use_ai=use_ai, index=_cached_index(project_id, stored))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    log_usage(db, user_id, CHAT_ACTION, {"project_id": project_id, "mode": reply["mode"]})
    reply["ai_available_in_plan"] = use_ai
    return jsonify(reply), 200
