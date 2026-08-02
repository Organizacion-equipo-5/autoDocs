"""
app/middleware/auth.py
Decoradores de autenticación y autorización basados en JWT.
"""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from app.repository.user_repository import UserRepository


def jwt_required_custom(f):
    """Verifica JWT y carga el usuario activo desde la BD."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception as e:
            return jsonify({"error": "Token inválido o expirado", "detalle": str(e)}), 401

        user_id = get_jwt_identity()
        repo = UserRepository()
        user = repo.find_by_id(user_id)
        if not user or not user.get("activo"):
            return jsonify({"error": "Usuario no encontrado o inactivo"}), 401

        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    """Restringe el acceso a los roles especificados."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except Exception as e:
                return jsonify({"error": "Token inválido o expirado"}), 401

            claims = get_jwt()
            user_rol = claims.get("rol", "")
            if user_rol not in roles:
                return jsonify({
                    "error": "Sin permisos suficientes",
                    "requerido": list(roles),
                    "actual": user_rol,
                }), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user() -> dict | None:
    """Obtiene el usuario actual desde el JWT (helper para usar dentro de vistas)."""
    try:
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        return UserRepository().find_by_id(user_id)
    except Exception:
        return None


def get_current_user_id() -> str | None:
    try:
        verify_jwt_in_request()
        return get_jwt_identity()
    except Exception:
        return None
