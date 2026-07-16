"""
app/repository/iot_repository.py
Repositorio para dispositivos IoT y sus lecturas.
STUB — operativo pero sin lógica MQTT activa hasta que IOT_ENABLED=True.
"""
from bson import ObjectId
from .base_repository import BaseRepository
from app.models.iot_device import IoTDeviceModel, IoTReadingModel


class IoTDeviceRepository(BaseRepository):
    collection_name = IoTDeviceModel.COLLECTION

    def find_by_adulto(self, adulto_id: str) -> list:
        result = self.find_many({"adulto_id": ObjectId(adulto_id), "activo": True})
        return result["items"]


class IoTReadingRepository(BaseRepository):
    collection_name = IoTReadingModel.COLLECTION

    def find_by_device(self, device_id: str, page: int = 1, page_size: int = 50) -> dict:
        return self.find_many(
            {"device_id": ObjectId(device_id)},
            sort_field="timestamp",
            sort_order=-1,
            page=page,
            page_size=page_size,
        )

    def last_reading(self, device_id: str) -> dict | None:
        return self.col.find_one(
            {"device_id": ObjectId(device_id)},
            sort=[("timestamp", -1)],
        )

    def alertas_recientes(self, adulto_id: str, limite: int = 10) -> list:
        return list(
            self.col.find({"adulto_id": ObjectId(adulto_id), "alerta": True})
            .sort("timestamp", -1)
            .limit(limite)
        )
