"""
app/models/medication_log.py
Registro de cada toma de medicamento (confirmada, omitida o retrasada).
"""
from datetime import datetime, timezone
from bson import ObjectId


class MedicationLogModel:
    COLLECTION = "medication_logs"

    ESTADOS = ["tomado", "omitido", "retrasado", "pendiente"]

    @staticmethod
    def schema(
        medicamento_id: ObjectId,
        adulto_id: ObjectId,
        estado: str,
        hora_programada: datetime,
        hora_real: datetime = None,
        notas: str = "",
        registrado_por: ObjectId = None,  # quién marcó la toma
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "medicamento_id": medicamento_id,
            "adulto_id": adulto_id,
            "estado": estado,
            "hora_programada": hora_programada,
            "hora_real": hora_real or now if estado == "tomado" else None,
            "notas": notas,
            "registrado_por": registrado_por,
            "creado_en": now,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        if not doc:
            return {}
        result = dict(doc)
        result["_id"] = str(result["_id"])
        result["medicamento_id"] = str(result["medicamento_id"])
        result["adulto_id"] = str(result["adulto_id"])
        if result.get("registrado_por"):
            result["registrado_por"] = str(result["registrado_por"])
        return result
