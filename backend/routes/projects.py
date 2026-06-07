from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.file_handler import save_uploaded_project, clone_github_repo
from datetime import datetime
import uuid

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/', methods=['GET'])
@jwt_required()
def get_projects():
    user_id = get_jwt_identity()
    db = get_db()
    projects = list(db.projects.find({"user_id": user_id}, {"_id": 1, "name": 1, "language": 1, "status": 1, "created_at": 1, "stats": 1}))
    return jsonify(projects), 200

@projects_bp.route('/', methods=['POST'])
@jwt_required()
def create_project():
    user_id = get_jwt_identity()
    db = get_db()

    # Obtener información del usuario
    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Solo aplicar límites a usuarios normales (no admin)
    if user.get('role') == 'user':
        plan = user.get('plan', 'free')
        project_limits = {
            'free': 3,
            'pro': 20,
            'enterprise': -1  # -1 significa ilimitado
        }
        limit = project_limits.get(plan, 3)

        # Contar proyectos actuales del usuario
        current_count = db.projects.count_documents({"user_id": user_id})

        # Verificar límite (si no es ilimitado)
        if limit != -1 and current_count >= limit:
            plan_names = {'free': 'Gratuito', 'pro': 'Pro', 'enterprise': 'Enterprise'}
            return jsonify({
                "error": f"Has alcanzado el límite de proyectos para tu plan {plan_names.get(plan, plan)}. Límite actual: {limit} proyectos."
            }), 400

    name = request.form.get('name', 'Unnamed Project')
    description = request.form.get('description', '')
    github_url = request.form.get('github_url', '')

    project_id = str(uuid.uuid4())
    project_path = None

    # Validar que se proporcione al menos archivo o URL
    has_file = 'file' in request.files and request.files['file'].filename

    if not has_file and not github_url:
        return jsonify({"error": "Debes proporcionar un archivo o una URL de GitHub"}), 400

    # Prioridad: archivo subido > URL de GitHub
    if has_file:
        f = request.files['file']
        try:
            project_path = save_uploaded_project(f, project_id)
        except Exception as e:
            return jsonify({"error": f"Failed to save uploaded project: {str(e)}"}), 500
    elif github_url:
        try:
            project_path = clone_github_repo(github_url, project_id)
        except Exception as e:
            return jsonify({"error": f"Failed to clone repository: {str(e)}"}), 400

    # Normalizar y verificar la ruta devuelta por los helpers
    from pathlib import Path
    try:
        if project_path:
            p = Path(project_path)
            # Resolver ruta absoluta para evitar problemas con el cwd en hilos
            project_path = str(p.resolve())
            if not p.exists():
                return jsonify({"error": "Project path does not exist after extraction/cloning"}), 500
    except Exception as e:
        return jsonify({"error": f"Invalid project path: {str(e)}"}), 500

    project = {
        "_id": project_id,
        "user_id": user_id,
        "name": name,
        "description": description,
        "github_url": github_url,
        "file_path": project_path,
        "status": "pending",
        "language": "unknown",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "stats": {
            "files": 0, "functions": 0,
            "classes": 0, "endpoints": 0,
            "quality_score": 0
        }
    }
    db.projects.insert_one(project)

    # Actualizar contador de proyectos del usuario
    new_count = db.projects.count_documents({"user_id": user_id})
    db.users.update_one({"_id": user_id}, {"$set": {"projects_count": new_count}})

    return jsonify({"id": project_id, "message": "Project created successfully"}), 201

@projects_bp.route('/<project_id>', methods=['GET'])
@jwt_required()
def get_project(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
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

    # Actualizar contador de proyectos del usuario
    new_count = db.projects.count_documents({"user_id": user_id})
    db.users.update_one({"_id": user_id}, {"$set": {"projects_count": new_count}})

    return jsonify({"message": "Project deleted"}), 200
