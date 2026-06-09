"""
app/models/user.py
Modelo de usuario con soporte para múltiples roles.
"""
from datetime import datetime, timezone
from bson import ObjectId


class UserModel:
    """Esquema lógico del documento Usuario en MongoDB."""

    COLLECTION = "users"

    ROLES = ["admin", "adulto", "familiar", "medico"]

    @staticmethod
    def schema(
        nombre: str,
        apellido: str,
        email: str,
        password_hash: str,
        rol: str,
        telefono: str = "",
        fecha_nacimiento: datetime = None,
        activo: bool = True,
    ) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "nombre": nombre,
            "apellido": apellido,
            "email": email.lower().strip(),
            "password_hash": password_hash,
            "rol": rol,
            "telefono": telefono,
            "fecha_nacimiento": fecha_nacimiento,
            "activo": activo,
            # Relaciones
            "pacientes_vinculados": [],   # Para familiar y médico: lista de ObjectId de adultos
            "familiares_vinculados": [],  # Para adulto: lista de ObjectId de familiares
            "medico_asignado": None,      # Para adulto: ObjectId del médico
            # Preferencias de notificación
            "notificaciones": {
                "email": True,
                "push": False,
            },
            # Metadatos
            "ultimo_login": None,
            "creado_en": now,
            "actualizado_en": now,
        }

    @staticmethod
    def to_response(doc: dict) -> dict:
        """Versión segura del documento (sin hash de contraseña)."""
        if not doc:
            return {}
        result = {k: v for k, v in doc.items() if k != "password_hash"}
        if "_id" in result:
            result["_id"] = str(result["_id"])
        if "pacientes_vinculados" in result:
            result["pacientes_vinculados"] = [str(x) for x in result["pacientes_vinculados"]]
        if "familiares_vinculados" in result:
            result["familiares_vinculados"] = [str(x) for x in result["familiares_vinculados"]]
        if "medico_asignado" in result and result["medico_asignado"]:
            result["medico_asignado"] = str(result["medico_asignado"])
        return result
