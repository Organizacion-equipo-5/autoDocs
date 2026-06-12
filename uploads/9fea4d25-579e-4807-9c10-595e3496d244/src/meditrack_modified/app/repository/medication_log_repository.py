"""
app/repository/medication_log_repository.py
"""
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from .base_repository import BaseRepository
from app.models.medication_log import MedicationLogModel


class MedicationLogRepository(BaseRepository):
    collection_name = MedicationLogModel.COLLECTION

    def find_by_adulto(self, adulto_id: str, page: int = 1, page_size: int = 20) -> dict:
        return self.find_many(
            {"adulto_id": ObjectId(adulto_id)},
            sort_field="hora_programada",
            sort_order=-1,
            page=page,
            page_size=page_size,
        )

    def find_by_medicamento(self, med_id: str, page: int = 1, page_size: int = 20) -> dict:
        return self.find_many(
            {"medicamento_id": ObjectId(med_id)},
            sort_field="hora_programada",
            sort_order=-1,
            page=page,
            page_size=page_size,
        )

    def tomas_hoy(self, adulto_id: str) -> list:
        hoy_inicio = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        hoy_fin = hoy_inicio + timedelta(days=1)
        return list(
            self.col.find({
                "adulto_id": ObjectId(adulto_id),
                "hora_programada": {"$gte": hoy_inicio, "$lt": hoy_fin},
            }).sort("hora_programada", 1)
        )

    def adherencia(self, adulto_id: str, dias: int = 30) -> dict:
        """Calcula porcentaje de adherencia de los últimos N días."""
        desde = datetime.now(timezone.utc) - timedelta(days=dias)
        pipeline = [
            {
                "$match": {
                    "adulto_id": ObjectId(adulto_id),
                    "hora_programada": {"$gte": desde},
                    "estado": {"$ne": "pendiente"},
                }
            },
            {
                "$group": {
                    "_id": "$estado",
                    "count": {"$sum": 1},
                }
            },
        ]
        resultados = list(self.col.aggregate(pipeline))
        counts = {r["_id"]: r["count"] for r in resultados}
        total = sum(counts.values())
        tomados = counts.get("tomado", 0)
        return {
            "total": total,
            "tomados": tomados,
            "omitidos": counts.get("omitido", 0),
            "retrasados": counts.get("retrasado", 0),
            "porcentaje": round((tomados / total * 100) if total else 0, 1),
        }

    def omisiones_recientes(self, adulto_id: str, horas: int = 24) -> list:
        desde = datetime.now(timezone.utc) - timedelta(hours=horas)
        return list(
            self.col.find({
                "adulto_id": ObjectId(adulto_id),
                "estado": "omitido",
                "hora_programada": {"$gte": desde},
            })
        )
