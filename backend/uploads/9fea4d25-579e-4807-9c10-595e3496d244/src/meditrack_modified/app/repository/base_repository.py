"""
app/repository/base_repository.py
Repositorio base con operaciones CRUD genéricas sobre MongoDB.
"""
from datetime import datetime, timezone
from bson import ObjectId
from flask import current_app
from flask_pymongo import PyMongo

# Instancia compartida, se inicializa en create_app()
mongo: PyMongo = None


def get_db():
    """Devuelve la base de datos activa."""
    return mongo.db


class BaseRepository:
    """CRUD genérico para una colección de MongoDB."""

    collection_name: str = ""

    def __init__(self):
        self.db = get_db()
        self.col = self.db[self.collection_name]

    # ------------------------------------------------------------------
    # Crear
    # ------------------------------------------------------------------
    def create(self, document: dict) -> dict:
        result = self.col.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    # ------------------------------------------------------------------
    # Leer
    # ------------------------------------------------------------------
    def find_by_id(self, doc_id: str) -> dict | None:
        try:
            oid = ObjectId(doc_id)
        except Exception:
            return None
        return self.col.find_one({"_id": oid})

    def find_one(self, query: dict) -> dict | None:
        return self.col.find_one(query)

    def find_many(
        self,
        query: dict,
        sort_field: str = "creado_en",
        sort_order: int = -1,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        total = self.col.count_documents(query)
        skip = (page - 1) * page_size
        cursor = (
            self.col.find(query)
            .sort(sort_field, sort_order)
            .skip(skip)
            .limit(page_size)
        )
        return {
            "items": list(cursor),
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),  # ceil division
        }

    def count(self, query: dict = None) -> int:
        return self.col.count_documents(query or {})

    # ------------------------------------------------------------------
    # Actualizar
    # ------------------------------------------------------------------
    def update_by_id(self, doc_id: str, updates: dict) -> bool:
        try:
            oid = ObjectId(doc_id)
        except Exception:
            return False
        updates["actualizado_en"] = datetime.now(timezone.utc)
        result = self.col.update_one({"_id": oid}, {"$set": updates})
        return result.modified_count > 0

    def update_one(self, query: dict, updates: dict) -> bool:
        updates.setdefault("actualizado_en", datetime.now(timezone.utc))
        result = self.col.update_one(query, {"$set": updates})
        return result.modified_count > 0

    # ------------------------------------------------------------------
    # Eliminar (soft delete preferido)
    # ------------------------------------------------------------------
    def soft_delete(self, doc_id: str) -> bool:
        return self.update_by_id(doc_id, {"activo": False})

    def hard_delete(self, doc_id: str) -> bool:
        try:
            oid = ObjectId(doc_id)
        except Exception:
            return False
        result = self.col.delete_one({"_id": oid})
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def exists(self, query: dict) -> bool:
        return self.col.count_documents(query, limit=1) > 0
