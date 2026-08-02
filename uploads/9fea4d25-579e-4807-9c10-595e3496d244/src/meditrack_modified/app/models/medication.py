"""
app/models/medication.py
Modelo de medicamento prescrito a un adulto mayor.
"""
from datetime import datetime, timezone
from bson import ObjectId


class MedicationModel:
    COLLECTION = "medications"

    FRECUENCIAS = ["cada_hora", "cada_2h", "cada_4h", "cada_6h", "cada_8h",
                   "cada_12h", "cada_24h", "personalizado"]

    FORMAS = ["tableta", "capsula", "jarabe", "inyeccion", "inhalador",
              "gotas", "parche", "crema", "supositorio", "otro"]

    @staticmethod
    def schema(
        adulto_id: ObjectId,
        nombre: str,
        forma: str,
        dosis: str,
        frecuencia: str,
        horarios: list,          # ["08:00", "14:00", "20:00"]
        fecha_inicio: datetime,
        fecha_fin: datetime = None,
        indicaciones: str = "",
        prescrito_por: ObjectId = None,
        con_alimentos: bool = False,
        activo: bool = True,
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "adulto_id": adulto_id,
            "nombre": nombre,
            "forma": forma,
            "dosis": dosis,
            "frecuencia": frecuencia,
            "horarios": horarios,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "indicaciones": indicaciones,
            "prescrito_por": prescrito_por,
            "con_alimentos": con_alimentos,
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
        if result.get("prescrito_por"):
            result["prescrito_por"] = str(result["prescrito_por"])
        return result
