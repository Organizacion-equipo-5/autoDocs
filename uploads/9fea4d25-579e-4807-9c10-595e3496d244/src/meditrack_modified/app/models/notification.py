"""
app/models/notification.py
Modelo de notificación enviada a usuarios.
"""
from datetime import datetime, timezone
from bson import ObjectId


class NotificationModel:
    COLLECTION = "notifications"

    TIPOS = [
        "recordatorio_medicamento",
        "toma_omitida",
        "alerta_iot",
        "nuevo_vinculo",
        "mensaje_medico",
        "sistema",
    ]

    CANALES = ["email", "push", "in_app"]

    @staticmethod
    def schema(
        destinatario_id: ObjectId,
        tipo: str,
        titulo: str,
        mensaje: str,
        canal: str = "in_app",
        referencia_id: ObjectId = None,   # ID del med / log / device relacionado
        referencia_tipo: str = "",
        enviada: bool = False,
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "destinatario_id": destinatario_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "canal": canal,
            "referencia_id": referencia_id,
            "referencia_tipo": referencia_tipo,
            "enviada": enviada,
            "leida": False,
            "creado_en": now,
            "enviado_en": None,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        if not doc:
            return {}
        result = dict(doc)
        result["_id"] = str(result["_id"])
        result["destinatario_id"] = str(result["destinatario_id"])
        if result.get("referencia_id"):
            result["referencia_id"] = str(result["referencia_id"])
        return result
