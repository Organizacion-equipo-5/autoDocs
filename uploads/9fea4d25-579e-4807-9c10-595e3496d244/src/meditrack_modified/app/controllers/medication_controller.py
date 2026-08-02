"""
app/controllers/medication_controller.py
CRUD de medicamentos de un adulto mayor.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services.medication_service import MedicationService
from app.middleware.auth import roles_required
from app.utils.responses import success, created, error, not_found, forbidden, paginated

med_bp = Blueprint("medications", __name__, url_prefix="/api/v1/medicamentos")
med_service = MedicationService()


@med_bp.post("/")
@jwt_required()
@roles_required("admin", "medico", "adulto", "familiar")
def crear_medicamento():
    """
    POST /api/v1/medicamentos/
    Body: { adulto_id, nombre, forma, dosis, frecuencia, horarios[], fecha_inicio, ... }
    """
    data = request.get_json(silent=True) or {}
    adulto_id = data.pop("adulto_id", None)
    if not adulto_id:
        return error("adulto_id es requerido")

    current_id = get_jwt_identity()
    med, err = med_service.create_medication(adulto_id, data, current_id)
    if err:
        return error(err)
    return created(med, "Medicamento registrado")


@med_bp.get("/adulto/<adulto_id>")
@jwt_required()
def listar_medicamentos(adulto_id):
    """GET /api/v1/medicamentos/adulto/<id>?solo_activos=true"""
    solo_activos = request.args.get("solo_activos", "true").lower() == "true"
    meds = med_service.get_medications(adulto_id, solo_activos)
    return success(meds)


@med_bp.get("/<med_id>")
@jwt_required()
def get_medicamento(med_id):
    med = med_service.get_medication(med_id)
    if not med:
        return not_found("Medicamento")
    return success(med)


@med_bp.put("/<med_id>")
@jwt_required()
@roles_required("admin", "medico", "adulto", "familiar")
def actualizar_medicamento(med_id):
    data = request.get_json(silent=True) or {}
    med, err = med_service.update_medication(med_id, data)
    if err:
        return error(err)
    return success(med, "Medicamento actualizado")


@med_bp.delete("/<med_id>")
@jwt_required()
@roles_required("admin", "medico")
def desactivar_medicamento(med_id):
    ok = med_service.deactivate_medication(med_id)
    if not ok:
        return not_found("Medicamento")
    return success(message="Medicamento desactivado")
