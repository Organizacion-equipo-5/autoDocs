"""
app/controllers/iot_controller.py
API REST para dispositivos IoT y sus lecturas.
Los endpoints están activos; la conexión MQTT real requiere IOT_ENABLED=True.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.iot_service import IoTService
from app.middleware.auth import roles_required
from app.utils.responses import success, created, error, not_found, paginated

iot_bp = Blueprint("iot", __name__, url_prefix="/api/v1/iot")
iot_service = IoTService()


@iot_bp.post("/dispositivos")
@jwt_required()
@roles_required("adulto", "familiar", "medico", "admin")
def registrar_dispositivo():
    """
    POST /api/v1/iot/dispositivos
    Body: { adulto_id, tipo, nombre_dispositivo, mac_address?, topic_mqtt? }
    tipos: oximetro | glucometro | tensiómetro | bascula | pastillero_iot | ...
    """
    data = request.get_json(silent=True) or {}
    adulto_id = data.pop("adulto_id", None) or get_jwt_identity()
    device, err = iot_service.registrar_dispositivo(adulto_id, data)
    if err:
        return error(err)
    return created(device, "Dispositivo registrado")


@iot_bp.get("/dispositivos/adulto/<adulto_id>")
@jwt_required()
def mis_dispositivos(adulto_id):
    """GET /api/v1/iot/dispositivos/adulto/<id>"""
    devices = iot_service.mis_dispositivos(adulto_id)
    return success(devices)


@iot_bp.post("/dispositivos/<device_id>/lectura")
@jwt_required()
def registrar_lectura(device_id):
    """
    POST /api/v1/iot/dispositivos/<id>/lectura
    Body: { adulto_id, valores: {spo2: 98, pulso: 72}, unidades?: {spo2: "%"}, notas? }
    """
    data = request.get_json(silent=True) or {}
    adulto_id = data.pop("adulto_id", None) or get_jwt_identity()
    reading, err = iot_service.registrar_lectura(device_id, adulto_id, data)
    if err:
        return error(err)
    return created(reading, "Lectura registrada")


@iot_bp.get("/dispositivos/<device_id>/lecturas")
@jwt_required()
def historial_lecturas(device_id):
    """GET /api/v1/iot/dispositivos/<id>/lecturas?page=1&page_size=50"""
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))
    result = iot_service.historial_lecturas(device_id, page, page_size)
    return paginated(result["items"], result)


@iot_bp.get("/dispositivos/<device_id>/ultima-lectura")
@jwt_required()
def ultima_lectura(device_id):
    reading = iot_service.ultima_lectura(device_id)
    if not reading:
        return not_found("Lectura")
    return success(reading)


@iot_bp.get("/alertas/adulto/<adulto_id>")
@jwt_required()
def alertas(adulto_id):
    """GET /api/v1/iot/alertas/adulto/<id>"""
    alertas = iot_service.alertas_recientes(adulto_id)
    return success(alertas)


@iot_bp.get("/estado")
@jwt_required()
@roles_required("admin")
def estado_iot():
    """GET /api/v1/iot/estado — Estado del módulo IoT"""
    from flask import current_app
    return success({
        "iot_enabled": current_app.config.get("IOT_ENABLED", False),
        "broker_host": current_app.config.get("IOT_BROKER_HOST"),
        "broker_port": current_app.config.get("IOT_BROKER_PORT"),
        "nota": "Para activar MQTT establece IOT_ENABLED=True en .env",
    })
