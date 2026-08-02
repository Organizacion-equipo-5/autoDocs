"""
app/repository/user_repository.py
"""
from bson import ObjectId
from .base_repository import BaseRepository
from app.models.user import UserModel


class UserRepository(BaseRepository):
    collection_name = UserModel.COLLECTION

    def find_by_email(self, email: str) -> dict | None:
        return self.find_one({"email": email.lower().strip()})

    def find_by_rol(self, rol: str, activo: bool = True) -> list:
        result = self.find_many({"rol": rol, "activo": activo})
        return result["items"]

    def link_familiar(self, adulto_id: str, familiar_id: str) -> bool:
        """Vincula familiar↔adulto en ambos documentos."""
        a_oid = ObjectId(adulto_id)
        f_oid = ObjectId(familiar_id)
        self.col.update_one(
            {"_id": a_oid},
            {"$addToSet": {"familiares_vinculados": f_oid}},
        )
        self.col.update_one(
            {"_id": f_oid},
            {"$addToSet": {"pacientes_vinculados": a_oid}},
        )
        return True

    def unlink_familiar(self, adulto_id: str, familiar_id: str) -> bool:
        a_oid = ObjectId(adulto_id)
        f_oid = ObjectId(familiar_id)
        self.col.update_one({"_id": a_oid}, {"$pull": {"familiares_vinculados": f_oid}})
        self.col.update_one({"_id": f_oid}, {"$pull": {"pacientes_vinculados": a_oid}})
        return True

    def assign_medico(self, adulto_id: str, medico_id: str) -> bool:
        m_oid = ObjectId(medico_id)
        a_oid = ObjectId(adulto_id)
        self.col.update_one({"_id": a_oid}, {"$set": {"medico_asignado": m_oid}})
        self.col.update_one({"_id": m_oid}, {"$addToSet": {"pacientes_vinculados": a_oid}})
        return True

    def get_familiares_of_adulto(self, adulto_id: str) -> list:
        adulto = self.find_by_id(adulto_id)
        if not adulto:
            return []
        ids = adulto.get("familiares_vinculados", [])
        if not ids:
            return []
        return list(self.col.find({"_id": {"$in": ids}, "activo": True}))

    def update_last_login(self, user_id: str):
        from datetime import datetime, timezone
        self.update_by_id(user_id, {"ultimo_login": datetime.now(timezone.utc)})
