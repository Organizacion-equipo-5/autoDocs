"""
app/utils/responses.py
Helpers para respuestas JSON consistentes en toda la API.
"""
from flask import jsonify


def success(data=None, message: str = "OK", status_code: int = 200):
    body = {"ok": True, "message": message}
    if data is not None:
        body["data"] = data
    return jsonify(body), status_code


def created(data=None, message: str = "Recurso creado"):
    return success(data, message, 201)


def no_content():
    return "", 204


def error(message: str, status_code: int = 400, details=None):
    body = {"ok": False, "error": message}
    if details:
        body["details"] = details
    return jsonify(body), status_code


def not_found(resource: str = "Recurso"):
    return error(f"{resource} no encontrado", 404)


def unauthorized(message: str = "No autenticado"):
    return error(message, 401)


def forbidden(message: str = "Sin permisos"):
    return error(message, 403)


def paginated(items: list, pagination: dict, message: str = "OK"):
    return jsonify({
        "ok": True,
        "message": message,
        "data": items,
        "pagination": {
            "total": pagination.get("total", 0),
            "page": pagination.get("page", 1),
            "page_size": pagination.get("page_size", 20),
            "pages": pagination.get("pages", 1),
        },
    }), 200
