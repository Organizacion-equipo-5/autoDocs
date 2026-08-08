# utils/project_timeout.py
from datetime import datetime, timedelta

# Tiempo máximo (en minutos) que un proyecto puede estar en
# "pending" o "analyzing" antes de marcarse automáticamente como error.
STALE_TIMEOUT_MINUTES = 5


def mark_stale_projects_as_error(db, extra_filter=None):
    """
    Marca como 'error' los proyectos que llevan más de STALE_TIMEOUT_MINUTES
    minutos en estado 'pending' o 'analyzing' sin actualizarse.

    Se ejecuta de forma "perezosa": cada vez que se consulta la lista de
    proyectos o el estado de uno en particular, se revisa primero si hay
    proyectos "atascados" y se corrigen antes de devolver la respuesta.

    Args:
        db: instancia de la base de datos (get_db()).
        extra_filter: dict opcional para acotar la búsqueda,
                      ej. {"user_id": user_id} o {"_id": project_id}.

    Returns:
        int: cantidad de proyectos actualizados.
    """
    threshold_iso = (datetime.utcnow() - timedelta(minutes=STALE_TIMEOUT_MINUTES)).isoformat()

    query = {
        "status": {"$in": ["pending", "analyzing"]},
        "$or": [
            {"updated_at": {"$lt": threshold_iso}},
            {"updated_at": {"$exists": False}, "created_at": {"$lt": threshold_iso}}
        ]
    }
    if extra_filter:
        query.update(extra_filter)

    result = db.projects.update_many(
        query,
        {"$set": {
            "status": "error",
            "error_message": (
                f"El proyecto superó el tiempo máximo de espera "
                f"({STALE_TIMEOUT_MINUTES} minutos) y fue marcado como error automáticamente."
            ),
            "updated_at": datetime.utcnow().isoformat()
        }}
    )
    return result.modified_count