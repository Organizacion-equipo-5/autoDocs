from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.file_handler import save_uploaded_project, clone_github_repo
from datetime import datetime
import uuid
from pathlib import Path

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/', methods=['GET'])
@jwt_required()
def get_projects():
    try:
        user_id = get_jwt_identity()
        print(f"[DEBUG] get_projects - user_id: {user_id}")
        db = get_db()
        projects = list(db.projects.find({"user_id": user_id}, {"_id": 1, "name": 1, "language": 1, "status": 1, "created_at": 1, "stats": 1}))
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

    project_id = str(uuid.uuid4())
    project_path = None

    has_file = 'file' in request.files and request.files['file'].filename

    if not has_file and not github_url:
        return jsonify({"error": "Debes proporcionar un archivo o una URL de GitHub"}), 400

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

    try:
        if project_path:
            p = Path(project_path)
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
        },
        "contributors": [],
        "contributors_stats": {
            "total_commits": 0,
            "unique_authors": 0
        }
    }
    db.projects.insert_one(project)

    if github_url:
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

    return jsonify({"id": project_id, "message": "Project created successfully"}), 201

@projects_bp.route('/<project_id>', methods=['GET'])
@jwt_required()
def get_project(project_id):
    user_id = get_jwt_identity()
    db = get_db()
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