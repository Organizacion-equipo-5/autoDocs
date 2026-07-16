"""
app/repository/medication_repository.py
"""
from bson import ObjectId
from .base_repository import BaseRepository
from app.models.medication import MedicationModel


class MedicationRepository(BaseRepository):
    collection_name = MedicationModel.COLLECTION

    def find_by_adulto(self, adulto_id: str, solo_activos: bool = True) -> list:
        query = {"adulto_id": ObjectId(adulto_id)}
        if solo_activos:
            query["activo"] = True
        result = self.find_many(query, sort_field="nombre", sort_order=1, page_size=100)
        return result["items"]

    def find_activos_con_horario(self) -> list:
        """Todos los medicamentos activos (para el scheduler de recordatorios)."""
        return list(self.col.find({"activo": True}))
