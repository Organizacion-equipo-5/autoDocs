"""
app/services/auth_service.py
Lógica de negocio para autenticación y gestión de sesiones.
"""
from datetime import datetime, timezone
from flask import current_app
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, create_refresh_token
from bson import ObjectId

from app.repository.user_repository import UserRepository
from app.models.user import UserModel
from app.utils.validators import is_valid_email, is_strong_password

bcrypt = Bcrypt()


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def register(self, data: dict) -> tuple[dict, str | None]:
        """
        Registra nuevo usuario.
        Retorna (usuario, error_message).
        """
        nombre = data.get("nombre", "").strip()
        apellido = data.get("apellido", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        rol = data.get("rol", "adulto")
        telefono = data.get("telefono", "")

        # Validaciones
        if not all([nombre, apellido, email, password]):
            return None, "Nombre, apellido, email y contraseña son requeridos"

        if not is_valid_email(email):
            return None, "Email inválido"

        if not is_strong_password(password):
            return None, "La contraseña debe tener al menos 8 caracteres, una letra y un número"

        valid_roles = current_app.config.get("VALID_ROLES", UserModel.ROLES)
        if rol not in valid_roles:
            return None, f"Rol inválido. Opciones: {', '.join(valid_roles)}"

        if self.user_repo.exists({"email": email}):
            return None, "Ya existe una cuenta con ese email"

        pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        doc = UserModel.schema(
            nombre=nombre,
            apellido=apellido,
            email=email,
            password_hash=pw_hash,
            rol=rol,
            telefono=telefono,
        )
        created = self.user_repo.create(doc)
        return UserModel.to_response(created), None

    def login(self, email: str, password: str) -> tuple[dict | None, str | None]:
        """
        Autentica al usuario.
        Retorna (tokens_dict, error_message).
        """
        user = self.user_repo.find_by_email(email)
        if not user:
            return None, "Email o contraseña incorrectos"

        if not user.get("activo"):
            return None, "Cuenta desactivada. Contacta al administrador"

        if not bcrypt.check_password_hash(user["password_hash"], password):
            return None, "Email o contraseña incorrectos"

        user_id = str(user["_id"])
        additional_claims = {
            "rol": user["rol"],
            "nombre": user["nombre"],
            "apellido": user["apellido"],
        }

        access_token = create_access_token(identity=user_id, additional_claims=additional_claims)
        refresh_token = create_refresh_token(identity=user_id, additional_claims=additional_claims)

        self.user_repo.update_last_login(user_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": UserModel.to_response(user),
        }, None

    def refresh_token(self, user_id: str) -> dict | None:
        user = self.user_repo.find_by_id(user_id)
        if not user or not user.get("activo"):
            return None
        additional_claims = {"rol": user["rol"], "nombre": user["nombre"], "apellido": user["apellido"]}
        return {"access_token": create_access_token(identity=user_id, additional_claims=additional_claims)}

    def change_password(self, user_id: str, old_password: str, new_password: str) -> str | None:
        user = self.user_repo.find_by_id(user_id)
        if not user:
            return "Usuario no encontrado"
        if not bcrypt.check_password_hash(user["password_hash"], old_password):
            return "Contraseña actual incorrecta"
        if not is_strong_password(new_password):
            return "La nueva contraseña debe tener al menos 8 caracteres, una letra y un número"
        new_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
        self.user_repo.update_by_id(user_id, {"password_hash": new_hash})
        return None
