"""
app/models/iot_device.py
Modelo de dispositivo IoT vinculado a un adulto mayor.

ESTADO: STUB — listo para implementación futura.
Los campos están definidos pero la lógica de conexión MQTT
se activará cuando IOT_ENABLED=True en el .env.

Dispositivos soportados planificados:
  - Oxímetro de pulso
  - Glucómetro
  - Tensiómetro
  - Báscula inteligente
  - Pastillero inteligente
  - Pulsera de actividad
"""
from datetime import datetime, timezone
from bson import ObjectId


class IoTDeviceModel:
    COLLECTION = "iot_devices"

    TIPOS = [
        "oximetro",
        "glucometro",
        "tensiómetro",
        "bascula",
        "pastillero_iot",
        "pulsera_actividad",
        "termometro",
        "otro",
    ]

    ESTADOS_CONEXION = ["conectado", "desconectado", "sin_configurar", "error"]

    @staticmethod
    def schema(
        adulto_id: ObjectId,
        tipo: str,
        nombre_dispositivo: str,
        mac_address: str = "",
        topic_mqtt: str = "",
        activo: bool = True,
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "adulto_id": adulto_id,
            "tipo": tipo,
            "nombre_dispositivo": nombre_dispositivo,
            "mac_address": mac_address,
            "topic_mqtt": topic_mqtt,
            "estado_conexion": "sin_configurar",
            "ultimo_dato": None,
            "ultima_lectura": None,
            "activo": activo,
            "creado_en": now,
            "actualizado_en": now,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        if not doc:
            return {}
        result = dict(doc)
        result["_id"] = str(result["_id"])
        result["adulto_id"] = str(result["adulto_id"])
        return result


class IoTReadingModel:
    """Lectura individual de un dispositivo IoT."""

    COLLECTION = "iot_readings"

    @staticmethod
    def schema(
        device_id: ObjectId,
        adulto_id: ObjectId,
        tipo: str,
        valores: dict,          # {"spo2": 98, "pulso": 72}  /  {"glucosa": 105}  / etc.
        unidades: dict = None,  # {"spo2": "%", "pulso": "bpm"}
        alerta: bool = False,
        notas: str = "",
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "device_id": device_id,
            "adulto_id": adulto_id,
            "tipo": tipo,
            "valores": valores,
            "unidades": unidades or {},
            "alerta": alerta,
            "notas": notas,
            "timestamp": now,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        if not doc:
            return {}
        result = dict(doc)
        result["_id"] = str(result["_id"])
        result["device_id"] = str(result["device_id"])
        result["adulto_id"] = str(result["adulto_id"])
        return result
