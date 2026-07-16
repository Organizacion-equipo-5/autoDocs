"""
app/controllers/user_controller.py
CRUD de usuarios, vínculos entre roles.
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services.user_service import UserService
from app.middleware.auth import roles_required
from app.utils.responses import success, error, not_found, paginated, forbidden

user_bp = Blueprint("users", __name__, url_prefix="/api/v1/usuarios")
user_service = UserService()


@user_bp.get("/")
@jwt_required()
@roles_required("admin")
def listar_usuarios():
    """GET /api/v1/usuarios/?rol=adulto&page=1&page_size=20"""
    rol = request.args.get("rol")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    result = user_service.list_users(rol=rol, page=page, page_size=page_size)
    return paginated(result["items"], result)


@user_bp.get("/me")
@jwt_required()
def mi_perfil():
    """GET /api/v1/usuarios/me"""
    user_id = get_jwt_identity()
    user = user_service.get_user(user_id)
    if not user:
        return not_found("Usuario")
    return success(user)


@user_bp.put("/me")
@jwt_required()
def actualizar_mi_perfil():
    """PUT /api/v1/usuarios/me"""
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    user, err = user_service.update_profile(user_id, data)
    if err:
        return error(err)
    return success(user, "Perfil actualizado")


@user_bp.get("/<user_id>")
@jwt_required()
def get_usuario(user_id):
    """GET /api/v1/usuarios/<id> — Admin o el propio usuario"""
    claims = get_jwt()
    current_id = get_jwt_identity()
    if claims.get("rol") != "admin" and current_id != user_id:
        return forbidden()
    user = user_service.get_user(user_id)
    if not user:
        return not_found("Usuario")
    return success(user)


@user_bp.delete("/<user_id>")
@jwt_required()
@roles_required("admin")
def desactivar_usuario(user_id):
    """DELETE /api/v1/usuarios/<id> — Solo admin"""
    ok = user_service.deactivate_user(user_id)
    if not ok:
        return not_found("Usuario")
    return success(message="Usuario desactivado")


@user_bp.post("/<user_id>/activar")
@jwt_required()
@roles_required("admin")
def activar_usuario(user_id):
    ok = user_service.activate_user(user_id)
    return success(message="Usuario activado") if ok else not_found("Usuario")


# ------------------------------------------------------------------
# Vínculos
# ------------------------------------------------------------------
@user_bp.post("/<adulto_id>/vincular-familiar/<familiar_id>")
@jwt_required()
@roles_required("admin", "adulto", "familiar")
def vincular_familiar(adulto_id, familiar_id):
    ok, err = user_service.vincular_familiar(adulto_id, familiar_id)
    if err:
        return error(err)
    return success(message="Familiar vinculado correctamente")


@user_bp.delete("/<adulto_id>/vincular-familiar/<familiar_id>")
@jwt_required()
@roles_required("admin", "adulto", "familiar")
def desvincular_familiar(adulto_id, familiar_id):
    user_service.desvincular_familiar(adulto_id, familiar_id)
    return success(message="Familiar desvinculado")


@user_bp.post("/<adulto_id>/asignar-medico/<medico_id>")
@jwt_required()
@roles_required("admin", "medico")
def asignar_medico(adulto_id, medico_id):
    ok, err = user_service.asignar_medico(adulto_id, medico_id)
    if err:
        return error(err)
    return success(message="Médico asignado correctamente")


@user_bp.get("/<adulto_id>/familiares")
@jwt_required()
def get_familiares(adulto_id):
    claims = get_jwt()
    rol = claims.get("rol")
    current_id = get_jwt_identity()
    if rol not in ("admin", "medico") and current_id != adulto_id:
        return forbidden()
    familiares = user_service.get_familiares(adulto_id)
    return success(familiares)


@user_bp.get("/me/pacientes")
@jwt_required()
@roles_required("familiar", "medico", "admin")
def mis_pacientes():
    user_id = get_jwt_identity()
    pacientes = user_service.get_mis_pacientes(user_id)
    return success(pacientes)
