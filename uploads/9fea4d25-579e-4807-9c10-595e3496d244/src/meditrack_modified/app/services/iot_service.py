"""
app/services/iot_service.py
Servicio de dispositivos IoT.

ESTADO: STUB — los métodos están implementados para la API REST.
La conexión MQTT real se activa con IOT_ENABLED=True en .env.
Para conectar un dispositivo real:
  1. Instala paho-mqtt: pip install paho-mqtt
  2. Configura credenciales en .env
  3. Implementa MQTTClient en app/utils/mqtt_client.py
  4. Activa IOT_ENABLED=True
"""
from datetime import datetime, timezone
from bson import ObjectId
from flask import current_app

from app.repository.iot_repository import IoTDeviceRepository, IoTReadingRepository
from app.models.iot_device import IoTDeviceModel, IoTReadingModel
from app.services.notification_service import NotificationService

# Umbrales de alerta por tipo de sensor
UMBRALES = {
    "oximetro": {
        "spo2": {"min": 90, "max": 100},
        "pulso": {"min": 40, "max": 120},
    },
    "glucometro": {
        "glucosa": {"min": 70, "max": 180},
    },
    "tensiómetro": {
        "sistolica": {"min": 90, "max": 140},
        "diastolica": {"min": 60, "max": 90},
    },
    "termometro": {
        "temperatura": {"min": 35.0, "max": 37.5},
    },
}


class IoTService:
    def __init__(self):
        self.device_repo = IoTDeviceRepository()
        self.reading_repo = IoTReadingRepository()
        self.notif_service = NotificationService()

    # ------------------------------------------------------------------
    # Gestión de dispositivos
    # ------------------------------------------------------------------
    def registrar_dispositivo(self, adulto_id: str, data: dict) -> tuple[dict, str | None]:
        if not data.get("tipo") or not data.get("nombre_dispositivo"):
            return None, "tipo y nombre_dispositivo son requeridos"
        if data["tipo"] not in IoTDeviceModel.TIPOS:
            return None, f"tipo inválido. Opciones: {', '.join(IoTDeviceModel.TIPOS)}"

        doc = IoTDeviceModel.schema(
            adulto_id=ObjectId(adulto_id),
            tipo=data["tipo"],
            nombre_dispositivo=data["nombre_dispositivo"],
            mac_address=data.get("mac_address", ""),
            topic_mqtt=data.get("topic_mqtt", f"meditrack/{adulto_id}/{data['tipo']}"),
        )
        created = self.device_repo.create(doc)
        return IoTDeviceModel.to_response(created), None

    def mis_dispositivos(self, adulto_id: str) -> list:
        devices = self.device_repo.find_by_adulto(adulto_id)
        return [IoTDeviceModel.to_response(d) for d in devices]

    def actualizar_estado(self, device_id: str, estado: str) -> bool:
        if estado not in IoTDeviceModel.ESTADOS_CONEXION:
            return False
        return self.device_repo.update_by_id(device_id, {"estado_conexion": estado})

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    def registrar_lectura(self, device_id: str, adulto_id: str, data: dict) -> tuple[dict, str | None]:
        """
        Registra una lectura manual (o proveniente de MQTT cuando esté habilitado).
        Detecta automáticamente si los valores están fuera de rango.
        """
        device = self.device_repo.find_by_id(device_id)
        if not device:
            return None, "Dispositivo no encontrado"

        valores = data.get("valores")
        if not valores or not isinstance(valores, dict):
            return None, "Se requieren 'valores' como objeto. Ej: {\"spo2\": 98, \"pulso\": 72}"

        alerta = self._detectar_alerta(device["tipo"], valores)

        doc = IoTReadingModel.schema(
            device_id=ObjectId(device_id),
            adulto_id=ObjectId(adulto_id),
            tipo=device["tipo"],
            valores=valores,
            unidades=data.get("unidades", {}),
            alerta=alerta,
            notas=data.get("notas", ""),
        )
        created = self.reading_repo.create(doc)

        # Actualizar último dato del dispositivo
        self.device_repo.update_by_id(device_id, {
            "ultimo_dato": valores,
            "ultima_lectura": datetime.now(timezone.utc),
            "estado_conexion": "conectado",
        })

        # Notificar si hay alerta
        if alerta:
            self.notif_service.notificar_alerta_iot(adulto_id, device["tipo"], valores)

        return IoTReadingModel.to_response(created), None

    def historial_lecturas(self, device_id: str, page: int = 1, page_size: int = 50) -> dict:
        result = self.reading_repo.find_by_device(device_id, page, page_size)
        result["items"] = [IoTReadingModel.to_response(r) for r in result["items"]]
        return result

    def ultima_lectura(self, device_id: str) -> dict | None:
        reading = self.reading_repo.last_reading(device_id)
        return IoTReadingModel.to_response(reading) if reading else None

    def alertas_recientes(self, adulto_id: str) -> list:
        alertas = self.reading_repo.alertas_recientes(adulto_id)
        return [IoTReadingModel.to_response(a) for a in alertas]

    # ------------------------------------------------------------------
    # Detección de alertas
    # ------------------------------------------------------------------
    def _detectar_alerta(self, tipo: str, valores: dict) -> bool:
        umbrales = UMBRALES.get(tipo, {})
        for parametro, valor in valores.items():
            rango = umbrales.get(parametro)
            if rango and isinstance(valor, (int, float)):
                if valor < rango["min"] or valor > rango["max"]:
                    return True
        return False

    # ------------------------------------------------------------------
    # MQTT (STUB — implementar cuando IOT_ENABLED=True)
    # ------------------------------------------------------------------
    def conectar_mqtt(self):
        if not current_app.config.get("IOT_ENABLED"):
            current_app.logger.info("IoT deshabilitado. Activa IOT_ENABLED=True para conectar MQTT.")
            return
        # TODO: Implementar conexión MQTT
        # from app.utils.mqtt_client import MQTTClient
        # self.mqtt = MQTTClient(...)
        # self.mqtt.connect()
        current_app.logger.info("MQTT: conexión no implementada aún.")
