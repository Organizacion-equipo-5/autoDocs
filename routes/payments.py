from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from datetime import datetime

payments_bp = Blueprint('payments', __name__)

PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "projects_limit": 3,
        "analyses_per_month": 10,
        "export_pdf": False,
        "ai_enhanced": False,
    },
    "pro": {
        "name": "Pro",
        "price": 350,
        "projects_limit": 20,
        "analyses_per_month": 100,
        "export_pdf": True,
        "ai_enhanced": True,
    },
    "enterprise": {
        "name": "Enterprise",
        "price": 850,
        "projects_limit": -1,
        "analyses_per_month": -1,
        "export_pdf": True,
        "ai_enhanced": True,
    }
}


@payments_bp.route('/plans', methods=['GET'])
def get_plans():
    return jsonify(PLANS), 200


@payments_bp.route('/upgrade', methods=['POST'])
@jwt_required()
def upgrade():
    """Simula el pago y actualiza el plan del usuario."""
    user_id = get_jwt_identity()
    data = request.get_json()
    plan_key = data.get('plan')

    if plan_key not in PLANS:
        return jsonify({"error": "Plan inválido"}), 400

    # Validación mínima de la tarjeta (solo formato, no es real)
    card = data.get('card', {})
    if not card.get('number') or not card.get('expiry') or not card.get('cvv'):
        return jsonify({"error": "Datos de tarjeta incompletos"}), 400

    db = get_db()
    db.users.update_one(
        {"_id": user_id},
        {"$set": {
            "plan": plan_key,
            "plan_updated_at": datetime.utcnow().isoformat()
        }}
    )

    return jsonify({
        "message": f"Plan actualizado a {PLANS[plan_key]['name']} exitosamente",
        "plan": plan_key
    }), 200


@payments_bp.route('/my-plan', methods=['GET'])
@jwt_required()
def my_plan():
    user_id = get_jwt_identity()
    db = get_db()
    user = db.users.find_one({"_id": user_id}, {"password": 0})
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404

    plan_key = user.get('plan', 'free')
    return jsonify({
        "plan": plan_key,
        "details": PLANS.get(plan_key, PLANS['free']),
        "plan_updated_at": user.get('plan_updated_at'),
    }), 200


@payments_bp.route('/cancel', methods=['POST'])
@jwt_required()
def cancel():
    """Regresa el usuario al plan free."""
    user_id = get_jwt_identity()
    db = get_db()
    db.users.update_one(
        {"_id": user_id},
        {"$set": {
            "plan": "free",
            "plan_updated_at": datetime.utcnow().isoformat()
        }}
    )
    return jsonify({"message": "Suscripción cancelada, regresaste al plan Free"}), 200