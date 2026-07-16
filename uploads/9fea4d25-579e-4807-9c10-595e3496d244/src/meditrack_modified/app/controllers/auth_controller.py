"""
app/controllers/auth_controller.py
Endpoints de autenticación.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.auth_service import AuthService
from app.utils.responses import success, created, error, unauthorized

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()


@auth_bp.post("/registro")
def registro():
    """
    POST /api/v1/auth/registro
    Crea una nueva cuenta de usuario.
    Body: { nombre, apellido, email, password, rol, telefono? }
    """
    data = request.get_json(silent=True)
    if not data:
        return error("Body JSON requerido")

    user, err = auth_service.register(data)
    if err:
        return error(err)
    return created(user, "Cuenta creada exitosamente")


@auth_bp.post("/login")
def login():
    """
    POST /api/v1/auth/login
    Body: { email, password }
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")

    if not email or not password:
        return error("Email y contraseña requeridos")

    result, err = auth_service.login(email, password)
    if err:
        return unauthorized(err)
    return success(result, "Login exitoso")


@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    POST /api/v1/auth/refresh
    Header: Authorization: Bearer <refresh_token>
    """
    user_id = get_jwt_identity()
    tokens = auth_service.refresh_token(user_id)
    if not tokens:
        return unauthorized("No se pudo renovar el token")
    return success(tokens)


@auth_bp.post("/cambiar-password")
@jwt_required()
def cambiar_password():
    """
    POST /api/v1/auth/cambiar-password
    Body: { password_actual, password_nuevo }
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    err = auth_service.change_password(
        user_id,
        data.get("password_actual", ""),
        data.get("password_nuevo", ""),
    )
    if err:
        return error(err)
    return success(message="Contraseña actualizada")
