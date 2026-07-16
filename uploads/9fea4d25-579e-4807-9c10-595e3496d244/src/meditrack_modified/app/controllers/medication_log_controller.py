"""
app/controllers/medication_log_controller.py
Registro y consulta de tomas de medicamentos.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.medication_log_service import MedicationLogService
from app.middleware.auth import roles_required
from app.utils.responses import success, created, error, paginated

log_bp = Blueprint("medication_logs", __name__, url_prefix="/api/v1/tomas")
log_service = MedicationLogService()


@log_bp.post("/")
@jwt_required()
@roles_required("adulto", "familiar", "medico", "admin")
def registrar_toma():
    """
    POST /api/v1/tomas/
    Body: { medicamento_id, adulto_id, estado, hora_programada?, hora_real?, notas? }
    estados: tomado | omitido | retrasado | pendiente
    """
    data = request.get_json(silent=True) or {}
    current_id = get_jwt_identity()
    log, err = log_service.registrar_toma(data, current_id)
    if err:
        return error(err)
    return created(log, "Toma registrada")


@log_bp.get("/adulto/<adulto_id>")
@jwt_required()
def historial(adulto_id):
    """GET /api/v1/tomas/adulto/<id>?page=1&page_size=20"""
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    result = log_service.historial(adulto_id, page, page_size)
    return paginated(result["items"], result)


@log_bp.get("/adulto/<adulto_id>/hoy")
@jwt_required()
def tomas_hoy(adulto_id):
    """GET /api/v1/tomas/adulto/<id>/hoy"""
    tomas = log_service.tomas_hoy(adulto_id)
    return success(tomas)


@log_bp.get("/adulto/<adulto_id>/adherencia")
@jwt_required()
def adherencia(adulto_id):
    """GET /api/v1/tomas/adulto/<id>/adherencia?dias=30"""
    dias = int(request.args.get("dias", 30))
    stats = log_service.adherencia(adulto_id, dias)
    return success(stats)
