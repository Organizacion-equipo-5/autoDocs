"""
app/services/user_service.py
Gestión de usuarios, vínculos entre roles y perfil.
"""
from app.repository.user_repository import UserRepository
from app.models.user import UserModel
from app.utils.validators import is_valid_email


class UserService:
    def __init__(self):
        self.repo = UserRepository()

    def get_user(self, user_id: str) -> dict | None:
        user = self.repo.find_by_id(user_id)
        return UserModel.to_response(user) if user else None

    def list_users(self, rol: str = None, page: int = 1, page_size: int = 20) -> dict:
        query = {"activo": True}
        if rol:
            query["rol"] = rol
        result = self.repo.find_many(query, sort_field="nombre", sort_order=1,
                                     page=page, page_size=page_size)
        result["items"] = [UserModel.to_response(u) for u in result["items"]]
        return result

    def update_profile(self, user_id: str, data: dict) -> tuple[dict, str | None]:
        allowed = ["nombre", "apellido", "telefono", "fecha_nacimiento", "notificaciones"]
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return None, "No hay campos válidos para actualizar"
        self.repo.update_by_id(user_id, updates)
        updated = self.repo.find_by_id(user_id)
        return UserModel.to_response(updated), None

    def deactivate_user(self, user_id: str) -> bool:
        return self.repo.update_by_id(user_id, {"activo": False})

    def activate_user(self, user_id: str) -> bool:
        return self.repo.update_by_id(user_id, {"activo": True})

    # ------------------------------------------------------------------
    # Vínculos
    # ------------------------------------------------------------------
    def vincular_familiar(self, adulto_id: str, familiar_id: str) -> tuple[bool, str | None]:
        adulto = self.repo.find_by_id(adulto_id)
        familiar = self.repo.find_by_id(familiar_id)
        if not adulto or adulto.get("rol") != "adulto":
            return False, "Adulto no encontrado"
        if not familiar or familiar.get("rol") != "familiar":
            return False, "Familiar no encontrado"
        self.repo.link_familiar(adulto_id, familiar_id)
        return True, None

    def desvincular_familiar(self, adulto_id: str, familiar_id: str) -> bool:
        return self.repo.unlink_familiar(adulto_id, familiar_id)

    def asignar_medico(self, adulto_id: str, medico_id: str) -> tuple[bool, str | None]:
        adulto = self.repo.find_by_id(adulto_id)
        medico = self.repo.find_by_id(medico_id)
        if not adulto or adulto.get("rol") != "adulto":
            return False, "Adulto no encontrado"
        if not medico or medico.get("rol") != "medico":
            return False, "Médico no encontrado"
        self.repo.assign_medico(adulto_id, medico_id)
        return True, None

    def get_familiares(self, adulto_id: str) -> list:
        familiares = self.repo.get_familiares_of_adulto(adulto_id)
        return [UserModel.to_response(f) for f in familiares]

    def get_mis_pacientes(self, cuidador_id: str) -> list:
        cuidador = self.repo.find_by_id(cuidador_id)
        if not cuidador:
            return []
        ids = cuidador.get("pacientes_vinculados", [])
        if not ids:
            return []
        pacientes = list(self.repo.col.find({"_id": {"$in": ids}, "activo": True}))
        return [UserModel.to_response(p) for p in pacientes]
