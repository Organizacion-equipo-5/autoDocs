"""
app/controllers/notification_controller.py
Gestión de notificaciones del usuario autenticado.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.notification_service import NotificationService
from app.utils.responses import success, error, paginated

notif_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notificaciones")
notif_service = NotificationService()


@notif_bp.get("/")
@jwt_required()
def mis_notificaciones():
    """GET /api/v1/notificaciones/?no_leidas=false&page=1"""
    user_id = get_jwt_identity()
    solo_no_leidas = request.args.get("no_leidas", "false").lower() == "true"
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    result = notif_service.mis_notificaciones(user_id, solo_no_leidas, page, page_size)
    return paginated(result["items"], result)


@notif_bp.get("/conteo")
@jwt_required()
def conteo_no_leidas():
    """GET /api/v1/notificaciones/conteo"""
    user_id = get_jwt_identity()
    count = notif_service.no_leidas_count(user_id)
    return success({"no_leidas": count})


@notif_bp.put("/<notif_id>/leida")
@jwt_required()
def marcar_leida(notif_id):
    ok = notif_service.marcar_leida(notif_id)
    if not ok:
        return error("No se pudo marcar como leída", 404)
    return success(message="Notificación marcada como leída")


@notif_bp.put("/todas-leidas")
@jwt_required()
def marcar_todas_leidas():
    user_id = get_jwt_identity()
    count = notif_service.marcar_todas_leidas(user_id)
    return success({"marcadas": count}, "Notificaciones marcadas como leídas")
