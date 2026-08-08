# routes/projects.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.file_handler import save_uploaded_project, clone_github_repo
from utils.project_timeout import mark_stale_projects_as_error
from datetime import datetime
import uuid
from pathlib import Path
import subprocess
import shutil
import requests

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/', methods=['GET'])
@jwt_required()
def get_projects():
    try:
        user_id = get_jwt_identity()
        print(f"[DEBUG] get_projects - user_id: {user_id}")
        db = get_db()
        
        # Verificar si el usuario existe y su rol
        user = db.users.find_one({"_id": user_id})
        print(f"[DEBUG] get_projects - user exists: {user is not None}")
        if user:
            print(f"[DEBUG] get_projects - user email: {user.get('email')}, role: {user.get('role')}")
        
        # Si es admin, mostrar todos los proyectos
        if user and user.get('role') == 'admin':
            print(f"[DEBUG] get_projects - User is admin, returning all projects")
            # 🔑 Revisa y marca como error TODOS los proyectos atascados (todos los usuarios)
            stale_count = mark_stale_projects_as_error(db)
            if stale_count:
                print(f"[DEBUG] get_projects - {stale_count} proyecto(s) marcados como error por timeout")
            projects = list(db.projects.find({}, {"_id": 1, "name": 1, "language": 1, "status": 1, "created_at": 1, "stats": 1, "error_message": 1}))
        else:
            # 🔑 Revisa y marca como error SOLO los proyectos atascados de este usuario
            stale_count = mark_stale_projects_as_error(db, {"user_id": user_id})
            if stale_count:
                print(f"[DEBUG] get_projects - {stale_count} proyecto(s) del usuario marcados como error por timeout")
            # Usuario normal, solo sus proyectos
            projects = list(db.projects.find({"user_id": user_id}, {"_id": 1, "name": 1, "language": 1, "status": 1, "created_at": 1, "stats": 1, "error_message": 1}))
        
        print(f"[DEBUG] get_projects - found {len(projects)} projects")
        for p in projects:
            if '_id' in p:
                p['_id'] = str(p['_id'])
        return jsonify(projects), 200
    except Exception as e:
        print(f"[ERROR] get_projects - Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@projects_bp.route('/', methods=['POST'])
@jwt_required()
def create_project():
    user_id = get_jwt_identity()
    db = get_db()

    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get('role') == 'user':
        plan = user.get('plan', 'free')
        project_limits = {
            'free': 3,
            'pro': 20,
            'enterprise': -1
        }
        limit = project_limits.get(plan, 3)
        current_count = db.projects.count_documents({"user_id": user_id})

        if limit != -1 and current_count >= limit:
            plan_names = {'free': 'Gratuito', 'pro': 'Pro', 'enterprise': 'Enterprise'}
            return jsonify({
                "error": f"Has alcanzado el límite de proyectos para tu plan {plan_names.get(plan, plan)}. Límite actual: {limit} proyectos."
            }), 400

    name = request.form.get('name', 'Unnamed Project')
    description = request.form.get('description', '')
    github_url = request.form.get('github_url', '')

    # Check for duplicate project name globally (all users)
    existing_project = db.projects.find_one({"name": name})
    if existing_project:
        return jsonify({"error": f"Ya existe un proyecto con el nombre '{name}'. Por favor usa un nombre diferente."}), 400

    project_id = str(uuid.uuid4())
    project_path = None
    error_message = None  # 🔑 En vez de cortar el flujo con un 500, guardamos el motivo del error

    has_file = 'file' in request.files and request.files['file'].filename

    if not has_file and not github_url:
        return jsonify({"error": "Debes proporcionar un archivo o una URL de GitHub"}), 400

    if has_file:
        f = request.files['file']
        try:
            project_path = save_uploaded_project(f, project_id)
        except Exception as e:
            error_message = f"Error al guardar el archivo subido: {str(e)}"
    elif github_url:
        try:
            project_path = clone_github_repo(github_url, project_id)
        except Exception as e:
            error_message = f"Error al clonar el repositorio: {str(e)}"

    if project_path and not error_message:
        try:
            p = Path(project_path)
            project_path = str(p.resolve())
            if not p.exists():
                error_message = "La ruta del proyecto no existe después de la extracción/clonado"
        except Exception as e:
            error_message = f"Ruta de proyecto inválida: {str(e)}"

    # 🔑 El proyecto SIEMPRE se crea, aunque haya fallado la subida/clonado.
    # Si hubo error, nace directamente con status "error".
    project = {
        "_id": project_id,
        "user_id": user_id,
        "name": name,
        "description": description,
        "github_url": github_url,
        "file_path": project_path,
        "status": "error" if error_message else "pending",
        "language": "unknown",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "stats": {
            "files": 0, "functions": 0,
            "classes": 0, "endpoints": 0,
            "quality_score": 0
        },
        "contributors": [],
        "contributors_stats": {
            "total_commits": 0,
            "unique_authors": 0
        }
    }
    if error_message:
        project["error_message"] = error_message

    db.projects.insert_one(project)

    if github_url and not error_message:
        try:
            from services.github_client import get_contributors_from_api
            contributors_data = get_contributors_from_api(github_url)
            
            if contributors_data and contributors_data.get('contributors'):
                db.projects.update_one(
                    {"_id": project_id},
                    {"$set": {
                        "contributors": contributors_data.get('contributors', []),
                        "contributors_stats": {
                            "total_commits": contributors_data.get('total_commits', 0),
                            "unique_authors": contributors_data.get('unique_authors', 0)
                        }
                    }}
                )
        except Exception as e:
            print(f"[ERROR] Error obteniendo colaboradores iniciales: {e}")

    new_count = db.projects.count_documents({"user_id": user_id})
    db.users.update_one({"_id": user_id}, {"$set": {"projects_count": new_count}})

    if error_message:
        # Se devuelve 201 igual (el proyecto SÍ se creó), pero con el detalle del error
        # para que el frontend pueda mostrar feedback si quiere, sin romper el flujo.
        return jsonify({
            "id": project_id,
            "message": "Proyecto creado con errores",
            "error": error_message
        }), 201

    return jsonify({"id": project_id, "message": "Project created successfully"}), 201

@projects_bp.route('/<project_id>', methods=['GET'])
@jwt_required()
def get_project(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    # 🔑 Revisa si ESTE proyecto en particular quedó atascado antes de devolverlo
    mark_stale_projects_as_error(db, {"_id": project_id, "user_id": user_id})
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    if '_id' in project:
        project['_id'] = str(project['_id'])
    
    return jsonify(project), 200

@projects_bp.route('/<project_id>', methods=['DELETE'])
@jwt_required()
def delete_project(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    result = db.projects.delete_one({"_id": project_id, "user_id": user_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Project not found"}), 404
    db.analysis_results.delete_many({"project_id": project_id})

    new_count = db.projects.count_documents({"user_id": user_id})
    db.users.update_one({"_id": user_id}, {"$set": {"projects_count": new_count}})

    return jsonify({"message": "Project deleted"}), 200

@projects_bp.route('/<project_id>', methods=['PUT'])
@jwt_required()
def update_project(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    # Check for duplicate name globally (excluding current project)
    existing_project = db.projects.find_one({
        "name": name,
        "_id": {"$ne": project_id}
    })
    if existing_project:
        return jsonify({"error": f"Ya existe un proyecto con el nombre '{name}'. Por favor usa un nombre diferente."}), 400
    
    update_data = {"name": name}
    if description is not None:
        update_data["description"] = description
    
    db.projects.update_one(
        {"_id": project_id},
        {"$set": update_data}
    )
    
    return jsonify({"message": "Project updated successfully"}), 200

# ══════════════════════════════════════════════════════════
#  ENDPOINTS PARA COLABORADORES
# ══════════════════════════════════════════════════════════

@projects_bp.route('/<project_id>/contributors', methods=['GET'])
@jwt_required()
def get_project_contributors(project_id):
    """
    Obtiene los colaboradores de un proyecto desde GitHub
    """
    user_id = get_jwt_identity()
    db = get_db()
    
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    # Si ya tenemos colaboradores guardados, devolverlos
    if project.get('contributors') and len(project.get('contributors', [])) > 0:
        return jsonify({
            "contributors": project.get('contributors', []),
            "total_commits": project.get('contributors_stats', {}).get('total_commits', 0),
            "unique_authors": project.get('contributors_stats', {}).get('unique_authors', 0),
            "repo_url": project.get('github_url', ''),
            "repo_name": project.get('name', ''),
            "cached": True
        }), 200
    
    github_url = project.get('github_url')
    if not github_url:
        return jsonify({
            "contributors": [],
            "message": "Este proyecto no tiene URL de GitHub asociada"
        }), 200
    
    try:
        from services.github_client import get_contributors_from_api
        contributors_data = get_contributors_from_api(github_url)
        
        if contributors_data and contributors_data.get('contributors'):
            db.projects.update_one(
                {"_id": project_id},
                {"$set": {
                    "contributors": contributors_data.get('contributors', []),
                    "contributors_stats": {
                        "total_commits": contributors_data.get('total_commits', 0),
                        "unique_authors": contributors_data.get('unique_authors', 0)
                    }
                }}
            )
        
        return jsonify(contributors_data), 200
    except Exception as e:
        print(f"[ERROR] get_project_contributors: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": f"Error al obtener colaboradores: {str(e)}",
            "contributors": []
        }), 500

@projects_bp.route('/<project_id>/contributors/refresh', methods=['POST'])
@jwt_required()
def refresh_project_contributors(project_id):
    """
    Refresca los colaboradores de un proyecto desde GitHub (forzar actualización)
    """
    user_id = get_jwt_identity()
    db = get_db()
    
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    github_url = project.get('github_url')
    if not github_url:
        return jsonify({
            "error": "Este proyecto no tiene URL de GitHub asociada"
        }), 400
    
    try:
        from services.github_client import get_contributors_from_api
        contributors_data = get_contributors_from_api(github_url)
        
        if contributors_data:
            db.projects.update_one(
                {"_id": project_id},
                {"$set": {
                    "contributors": contributors_data.get('contributors', []),
                    "contributors_stats": {
                        "total_commits": contributors_data.get('total_commits', 0),
                        "unique_authors": contributors_data.get('unique_authors', 0)
                    }
                }}
            )
        
        return jsonify({
            "message": "Colaboradores actualizados correctamente",
            "contributors": contributors_data.get('contributors', []),
            "total_commits": contributors_data.get('total_commits', 0),
            "unique_authors": contributors_data.get('unique_authors', 0)
        }), 200
    except Exception as e:
        print(f"[ERROR] refresh_project_contributors: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": f"Error al actualizar colaboradores: {str(e)}"
        }), 500

@projects_bp.route('/<project_id>/sync', methods=['POST'])
@jwt_required()
def sync_project(project_id):
    """
    Sincroniza un proyecto con GitHub (git pull + re-análisis)
    Solo disponible para usuarios Pro y Enterprise
    """
    user_id = get_jwt_identity()
    db = get_db()

    # Verificar plan del usuario
    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    plan = user.get('plan', 'free')
    if plan == 'free':
        return jsonify({"error": "La función de sincronización con GitHub solo está disponible para planes Pro y Enterprise. Actualiza tu plan para usar esta función."}), 403

    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    github_url = project.get('github_url')
    if not github_url:
        return jsonify({"error": "Este proyecto no tiene URL de GitHub asociada"}), 400

    project_path = project.get('file_path')
    if not project_path or not Path(project_path).exists():
        return jsonify({"error": "Ruta del proyecto no encontrada"}), 400

    try:
        # Realizar git pull
        result = subprocess.run(
            ['git', 'pull'],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"[ERROR] git pull failed: {result.stderr}")
            return jsonify({"error": f"Error al hacer git pull: {result.stderr}"}), 400

        print(f"[INFO] git pull successful for project {project_id}")

        # Actualizar estado del proyecto
        db.projects.update_one(
            {"_id": project_id},
            {"$set": {
                "status": "pending",
                "updated_at": datetime.utcnow().isoformat()
            }}
        )

        # Iniciar nuevo análisis
        try:
            requests.post(
                f'http://127.0.0.1:5000/api/analysis/{project_id}/start',
                headers={'Authorization': request.headers.get('Authorization')},
                timeout=10
            )
        except:
            # Si falla el inicio asíncrono, continuar
            pass

        return jsonify({
            "message": "Proyecto sincronizado correctamente. El análisis comenzará pronto."
        }), 200

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout al hacer git pull"}), 400
    except Exception as e:
        print(f"[ERROR] sync_project: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error al sincronizar proyecto: {str(e)}"}), 500