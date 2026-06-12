"""
app/services/medication_log_service.py
Registro de tomas y cálculo de adherencia.
"""
from datetime import datetime, timezone
from bson import ObjectId

from app.repository.medication_log_repository import MedicationLogRepository
from app.repository.medication_repository import MedicationRepository
from app.models.medication_log import MedicationLogModel
from app.utils.validators import parse_date
from app.services.notification_service import NotificationService


class MedicationLogService:
    def __init__(self):
        self.log_repo = MedicationLogRepository()
        self.med_repo = MedicationRepository()
        self.notif_service = NotificationService()

    def registrar_toma(self, data: dict, registrado_por_id: str) -> tuple[dict, str | None]:
        med_id = data.get("medicamento_id")
        adulto_id = data.get("adulto_id")
        estado = data.get("estado")

        if not all([med_id, adulto_id, estado]):
            return None, "medicamento_id, adulto_id y estado son requeridos"

        if estado not in MedicationLogModel.ESTADOS:
            return None, f"Estado inválido. Opciones: {', '.join(MedicationLogModel.ESTADOS)}"

        med = self.med_repo.find_by_id(med_id)
        if not med:
            return None, "Medicamento no encontrado"

        hora_programada = parse_date(data.get("hora_programada")) if data.get("hora_programada") else datetime.now(timezone.utc)
        hora_real = parse_date(data.get("hora_real")) if data.get("hora_real") else None

        doc = MedicationLogModel.schema(
            medicamento_id=ObjectId(med_id),
            adulto_id=ObjectId(adulto_id),
            estado=estado,
            hora_programada=hora_programada,
            hora_real=hora_real,
            notas=data.get("notas", ""),
            registrado_por=ObjectId(registrado_por_id),
        )
        created = self.log_repo.create(doc)

        # Notificar familiares si se omitió
        if estado == "omitido":
            self.notif_service.notificar_omision(adulto_id, med["nombre"])

        return MedicationLogModel.to_response(created), None

    def historial(self, adulto_id: str, page: int = 1, page_size: int = 20) -> dict:
        result = self.log_repo.find_by_adulto(adulto_id, page, page_size)
        result["items"] = [MedicationLogModel.to_response(i) for i in result["items"]]
        return result

    def tomas_hoy(self, adulto_id: str) -> list:
        items = self.log_repo.tomas_hoy(adulto_id)
        return [MedicationLogModel.to_response(i) for i in items]

    def adherencia(self, adulto_id: str, dias: int = 30) -> dict:
        return self.log_repo.adherencia(adulto_id, dias)
