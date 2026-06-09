"""
app/repository/notification_repository.py
"""
from bson import ObjectId
from .base_repository import BaseRepository
from app.models.notification import NotificationModel


class NotificationRepository(BaseRepository):
    collection_name = NotificationModel.COLLECTION

    def find_by_usuario(self, usuario_id: str, solo_no_leidas: bool = False,
                        page: int = 1, page_size: int = 20) -> dict:
        query = {"destinatario_id": ObjectId(usuario_id)}
        if solo_no_leidas:
            query["leida"] = False
        return self.find_many(query, sort_field="creado_en", sort_order=-1,
                              page=page, page_size=page_size)

    def marcar_leida(self, notif_id: str) -> bool:
        return self.update_by_id(notif_id, {"leida": True})

    def marcar_todas_leidas(self, usuario_id: str) -> int:
        result = self.col.update_many(
            {"destinatario_id": ObjectId(usuario_id), "leida": False},
            {"$set": {"leida": True}},
        )
        return result.modified_count

    def no_leidas_count(self, usuario_id: str) -> int:
        return self.count({"destinatario_id": ObjectId(usuario_id), "leida": False})
