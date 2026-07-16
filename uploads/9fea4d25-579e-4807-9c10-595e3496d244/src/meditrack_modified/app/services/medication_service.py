"""
app/services/medication_service.py
Lógica de negocio para gestión de medicamentos.
"""
from datetime import datetime, timezone
from bson import ObjectId

from app.repository.medication_repository import MedicationRepository
from app.repository.user_repository import UserRepository
from app.models.medication import MedicationModel
from app.utils.validators import validate_required_fields, is_valid_hora, parse_date


class MedicationService:
    def __init__(self):
        self.med_repo = MedicationRepository()
        self.user_repo = UserRepository()

    def create_medication(self, adulto_id: str, data: dict, creado_por_id: str) -> tuple[dict, str | None]:
        missing = validate_required_fields(data, ["nombre", "forma", "dosis", "frecuencia", "horarios", "fecha_inicio"])
        if missing:
            return None, f"Campos requeridos: {', '.join(missing)}"

        adulto = self.user_repo.find_by_id(adulto_id)
        if not adulto or adulto.get("rol") != "adulto":
            return None, "Adulto no encontrado"

        horarios = data.get("horarios", [])
        if not isinstance(horarios, list) or not horarios:
            return None, "Se requiere al menos un horario (lista de strings HH:MM)"
        for h in horarios:
            if not is_valid_hora(h):
                return None, f"Horario inválido: '{h}'. Usa formato HH:MM"

        fecha_inicio = parse_date(data["fecha_inicio"])
        if not fecha_inicio:
            return None, "Formato de fecha_inicio inválido. Usa YYYY-MM-DD"
        fecha_fin = parse_date(data.get("fecha_fin")) if data.get("fecha_fin") else None

        prescrito_por = None
        if data.get("prescrito_por"):
            prescrito_por = ObjectId(data["prescrito_por"])
        else:
            creador = self.user_repo.find_by_id(creado_por_id)
            if creador and creador.get("rol") == "medico":
                prescrito_por = ObjectId(creado_por_id)

        doc = MedicationModel.schema(
            adulto_id=ObjectId(adulto_id),
            nombre=data["nombre"].strip(),
            forma=data["forma"],
            dosis=data["dosis"].strip(),
            frecuencia=data["frecuencia"],
            horarios=horarios,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            indicaciones=data.get("indicaciones", ""),
            prescrito_por=prescrito_por,
            con_alimentos=bool(data.get("con_alimentos", False)),
        )
        created = self.med_repo.create(doc)
        return MedicationModel.to_response(created), None

    def get_medications(self, adulto_id: str, solo_activos: bool = True) -> list:
        meds = self.med_repo.find_by_adulto(adulto_id, solo_activos)
        return [MedicationModel.to_response(m) for m in meds]

    def get_medication(self, med_id: str) -> dict | None:
        med = self.med_repo.find_by_id(med_id)
        return MedicationModel.to_response(med) if med else None

    def update_medication(self, med_id: str, data: dict) -> tuple[dict, str | None]:
        med = self.med_repo.find_by_id(med_id)
        if not med:
            return None, "Medicamento no encontrado"

        allowed_fields = ["nombre", "forma", "dosis", "frecuencia", "horarios",
                          "fecha_fin", "indicaciones", "con_alimentos", "activo"]
        updates = {}
        for field in allowed_fields:
            if field in data:
                if field == "horarios":
                    for h in data[field]:
                        if not is_valid_hora(h):
                            return None, f"Horario inválido: '{h}'"
                if field == "fecha_fin":
                    parsed = parse_date(data[field])
                    if not parsed:
                        return None, "Formato de fecha_fin inválido"
                    updates[field] = parsed
                else:
                    updates[field] = data[field]

        self.med_repo.update_by_id(med_id, updates)
        updated = self.med_repo.find_by_id(med_id)
        return MedicationModel.to_response(updated), None

    def deactivate_medication(self, med_id: str) -> bool:
        return self.med_repo.soft_delete(med_id)
