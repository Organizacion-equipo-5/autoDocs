"""
routes/plan_recommendation.py
Endpoint para obtener recomendación de plan personalizada
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.plan_recommender import recommend_plan_for_user
from services.db import get_db

plan_recommendation_bp = Blueprint("plan_recommendation", __name__)


@plan_recommendation_bp.route("/me", methods=["GET"])
@jwt_required()
def get_recommendation_for_current_user():
    """Obtiene la recomendación de plan para el usuario actual (autenticado).

    Este endpoint se registra con el prefijo `/api/plan-recommendation` en `app.py`,
    por lo que la ruta final será `/api/plan-recommendation/me`.
    """
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({"error": "No autorizado"}), 401

        db = get_db()
        data = recommend_plan_for_user(db, user_id)
        if "error" in data:
            return jsonify({"error": data["error"]}), 400
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500