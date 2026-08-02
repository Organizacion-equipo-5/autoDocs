from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from functools import wraps
from werkzeug.security import generate_password_hash
from datetime import datetime
import uuid
import re

admin_bp = Blueprint('admin', __name__)

STOPWORDS = {
    'de', 'la', 'el', 'que', 'y', 'a', 'en', 'los', 'se', 'del', 'las', 'por',
    'con', 'una', 'un', 'para', 'es', 'al', 'lo', 'como', 'su', 'más', 'o',
    'este', 'esta', 'entre', 'datos', 'proyecto', 'documentación', 'funciones',
    'clases', 'archivos', 'api', 'codigo', 'código', 'sistema', 'servicio',
    'método', 'metodo', 'modelo', 'archivo', 'ruta', 'base', 'función', 'funcion'
}


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        db = get_db()
        user_id = get_jwt_identity()
        user = db.users.find_one({"_id": user_id})
        if not user or user.get('role') != 'admin':
            return jsonify({"error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'\[.*?\]\(.*?\)', ' ', text)
    text = re.sub(r'[^a-z0-9_\s]', ' ', text.lower())
    return text


def top_terms(text: str, limit=12):
    if not isinstance(text, str):
        text = str(text)
    words = [w for w in re.split(r'\s+', normalize_text(text)) if w and len(w) > 3 and w not in STOPWORDS]
    freqs = {}
    for word in words:
        freqs[word] = freqs.get(word, 0) + 1
    return sorted(freqs.items(), key=lambda item: item[1], reverse=True)[:limit]


def extract_technical_terms(text: str, known_names=None, limit=12):
    known_names = set(known_names or [])
    tokens = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]{3,}\b', text))
    technical = []
    for token in sorted(tokens, key=lambda t: (-len(t), t)):
        if len(token) > 50:
            continue
        if re.match(r'^[a-f0-9]{32,}$', token.lower()):
            continue
        if re.match(r'^[a-z0-9]{20,}$', token.lower()):
            continue

        if token in known_names or '_' in token or re.search(r'[A-Z]', token) or token.endswith('ID') or token.endswith('Url'):
            lower = token.lower()
            if lower not in STOPWORDS and lower not in technical:
                technical.append(lower)
        elif token.lower() in known_names:
            technical.append(token.lower())
        if len(technical) >= limit:
            break
    return technical[:limit]


def common_terms(keywords, technical):
    return [term for term in keywords if term in technical][:12]


def find_user_by_identifier(db, identifier):
    if not identifier:
        return None
    user = db.users.find_one({"email": identifier})
    if user:
        return user
    return db.users.find_one({"_id": identifier})


# 🆕 Arma la lista de {"results", "project"} de todos los proyectos con análisis
def _get_all_projects_data(db):
    projects = list(db.projects.find({}))
    analyses = list(db.analysis_results.find({}))
    analysis_map = {a.get("project_id"): a for a in analyses if a.get("project_id")}

    data = []
    for project in projects:
        analysis = analysis_map.get(project.get("_id"))
        if analysis and analysis.get("results"):
            data.append({"results": analysis["results"], "project": project})
    return data


@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def admin_list_users():
    db = get_db()
    users = list(db.users.find({}, {"password": 0}))
    return jsonify([
        {
            "_id": user.get('_id'),
            "name": user.get('name'),
            "email": user.get('email'),
            "role": user.get('role', 'user'),
            "created_at": user.get('created_at'),
            "projects_count": user.get('projects_count', 0),
            "plan": user.get('plan', 'free')
        }
        for user in users
    ]), 200


@admin_bp.route('/users', methods=['POST'])
@jwt_required()
@admin_required
def admin_create_user():
    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')

    if not name or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400

    db = get_db()
    if db.users.find_one({"email": email}):
        return jsonify({"error": "Email already registered"}), 409

    user = {
        "_id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "password": generate_password_hash(password),
        "created_at": datetime.utcnow().isoformat(),
        "role": role,
        "projects_count": 0,
        "plan": "free"
    }
    db.users.insert_one(user)
    return jsonify({
        "_id": user['_id'],
        "name": user['name'],
        "email": user['email'],
        "role": user['role'],
        "created_at": user['created_at'],
        "projects_count": user['projects_count']
    }), 201


@admin_bp.route('/users/<user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def admin_update_user(user_id):
    data = request.get_json() or {}
    db = get_db()
    existing = db.users.find_one({"_id": user_id})
    if not existing:
        return jsonify({"error": "User not found"}), 404

    update = {}
    if data.get('name'):
        update['name'] = data.get('name')
    if data.get('email'):
        if db.users.find_one({"email": data['email'], "_id": {"$ne": user_id}}):
            return jsonify({"error": "Email already registered"}), 409
        update['email'] = data.get('email')
    if data.get('role'):
        update['role'] = data.get('role')
    if data.get('password'):
        update['password'] = generate_password_hash(data.get('password'))

    if update:
        db.users.update_one({"_id": user_id}, {"$set": update})
    return jsonify({"message": "User updated"}), 200


@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    result = db.users.delete_one({"_id": user_id})
    if result.deleted_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "User deleted"}), 200


@admin_bp.route('/projects', methods=['GET'])
@jwt_required()
@admin_required
def admin_list_projects():
    db = get_db()
    users = list(db.users.find({}, {"_id": 1, "name": 1}))
    user_map = {user['_id']: user['name'] for user in users}
    projects = list(db.projects.find({}))
    return jsonify([
        {
            "_id": project.get('_id'),
            "name": project.get('name'),
            "owner": user_map.get(project.get('user_id'), 'Desconocido'),
            "user_id": project.get('user_id'),
            "language": project.get('language'),
            "status": project.get('status'),
            "quality_score": project.get('stats', {}).get('quality_score') if project.get('stats') else None,
            "created_at": project.get('created_at')
        }
        for project in projects
    ]), 200


@admin_bp.route('/pca', methods=['GET'])
@jwt_required()
@admin_required
def admin_pca_analysis():
    db = get_db()
    analyses = list(db.analysis_results.find({}, {"project_id": 1, "results": 1}))
    if not analyses:
        return jsonify({
            "status": "ok",
            "pca": {
                "explained_variance_ratio": [],
                "project_coordinates": [],
                "conclusion": ["No hay suficientes proyectos para realizar el análisis PCA."],
                "sugerencias": ["Agrega más proyectos para obtener insights significativos."],
                "interpretacion": "PCA no disponible: se requieren al menos 2 proyectos."
            }
        }), 200

    project_map = {
        str(project['_id']): project.get('name', 'Desconocido')
        for project in db.projects.find({}, {"_id": 1, "name": 1})
    }

    try:
        from services.ml_analyzer import pca_analysis

        analyses_data = []
        for analysis in analyses:
            project_id = analysis.get('project_id')
            results = analysis.get('results', {})
            if results and project_id:
                analyses_data.append({
                    "project_id": project_id,
                    "results": results
                })

        if len(analyses_data) < 2:
            return jsonify({
                "status": "ok",
                "pca": {
                    "explained_variance_ratio": [],
                    "project_coordinates": [],
                    "conclusion": ["Se necesitan al menos 2 proyectos con análisis completos para PCA."],
                    "sugerencias": ["Ejecuta análisis en más proyectos para obtener insights significativos."],
                    "interpretacion": "PCA no disponible: se requieren al menos 2 proyectos analizados."
                }
            }), 200

        pca_result = pca_analysis(analyses_data, project_map=project_map, n_components=2)

        if "error" in pca_result:
            return jsonify({
                "status": "error",
                "message": pca_result["error"]
            }), 400

        conclusion = pca_result.get("conclusion", [])
        if isinstance(conclusion, str):
            conclusion = [conclusion]
        elif not isinstance(conclusion, list):
            conclusion = ["Análisis PCA completado correctamente."]

        sugerencias = pca_result.get("sugerencias", [])
        if isinstance(sugerencias, str):
            sugerencias = [sugerencias]
        elif not isinstance(sugerencias, list):
            sugerencias = ["Revisa la documentación del proyecto para identificar áreas de mejora."]

        project_coordinates = pca_result.get("project_coordinates", [])

        return jsonify({
            "status": "ok",
            "pca": {
                "explained_variance_ratio": pca_result.get("explained_variance_ratio", []),
                "project_coordinates": project_coordinates,
                "conclusion": conclusion,
                "sugerencias": sugerencias,
                "interpretacion": pca_result.get("interpretacion", "PCA completado correctamente.")
            }
        }), 200

    except Exception as e:
        print(f"Error en PCA: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error al calcular PCA: {str(e)}"
        }), 500


@admin_bp.route('/projects', methods=['POST'])
@jwt_required()
@admin_required
def admin_create_project():
    data = request.get_json() or {}
    name = data.get('name')
    owner = data.get('owner')
    language = data.get('language', 'Unknown')
    status = data.get('status', 'pending')

    if not name or not owner:
        return jsonify({"error": "Missing required fields"}), 400

    db = get_db()
    user = find_user_by_identifier(db, owner)
    if not user:
        return jsonify({"error": "Owner user not found"}), 404

    project = {
        "_id": str(uuid.uuid4()),
        "name": name,
        "user_id": user['_id'],
        "language": language,
        "status": status,
        "created_at": datetime.utcnow().isoformat(),
        "stats": {}
    }
    db.projects.insert_one(project)
    return jsonify({"message": "Project created", "project": project}), 201


@admin_bp.route('/projects/<project_id>', methods=['PUT'])
@jwt_required()
@admin_required
def admin_update_project(project_id):
    data = request.get_json() or {}
    db = get_db()
    project = db.projects.find_one({"_id": project_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    update = {}
    if data.get('name'):
        update['name'] = data.get('name')
    if data.get('owner'):
        user = find_user_by_identifier(db, data.get('owner'))
        if not user:
            return jsonify({"error": "Owner user not found"}), 404
        update['user_id'] = user['_id']
    if data.get('language'):
        update['language'] = data.get('language')
    if data.get('status'):
        update['status'] = data.get('status')

    if update:
        db.projects.update_one({"_id": project_id}, {"$set": update})
    return jsonify({"message": "Project updated"}), 200


@admin_bp.route('/projects/<project_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def admin_delete_project(project_id):
    db = get_db()
    result = db.projects.delete_one({"_id": project_id})
    if result.deleted_count == 0:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"message": "Project deleted"}), 200


@admin_bp.route('/overview', methods=['GET'])
@jwt_required()
@admin_required
def admin_overview():
    try:
        db = get_db()
        print(f"[Admin Overview] Iniciando cálculo de estadísticas")

        users = list(db.users.find({}, {"password": 0}))
        projects = list(db.projects.find({}, {}))
        analyses = list(db.analysis_results.find({}, {}))

        print(f"[Admin Overview] Usuarios: {len(users)}, Proyectos: {len(projects)}, Análisis: {len(analyses)}")

        total_users = len(users)
        total_projects = len(projects)

        completed_projects = 0
        pending_projects = 0
        errored_projects = 0
        quality_scores = []

        for p in projects:
            status = p.get('status')
            if status == 'completed':
                completed_projects += 1
            elif status == 'pending':
                pending_projects += 1
            elif status == 'error':
                errored_projects += 1

            qs = p.get('stats', {}).get('quality_score')
            if qs is not None and isinstance(qs, (int, float)):
                quality_scores.append(qs)

        average_quality = round(sum(quality_scores) / max(len(quality_scores), 1), 1) if quality_scores else 0

        language_distribution = {}
        for p in projects:
            lang = p.get('language') or 'Unknown'
            language_distribution[lang] = language_distribution.get(lang, 0) + 1

        from collections import defaultdict
        projects_per_month = defaultdict(int)
        for p in projects:
            created_at = p.get('created_at', '')
            if created_at:
                try:
                    month_key = str(created_at)[:7]
                    projects_per_month[month_key] += 1
                except Exception:
                    pass
        projects_per_month = dict(sorted(projects_per_month.items())[-12:])

        print(f"[Admin Overview] Stats de proyectos calculadas: completados={completed_projects}, calidad={average_quality}")

        docs_parts = []
        for analysis in analyses:
            doc = analysis.get('documentation', '')
            if doc:
                try:
                    docs_parts.append(str(doc))
                except Exception as e:
                    print(f"[Admin Overview] Error processing documentation: {e}")
        docs_text = ' '.join(docs_parts)

        max_text_length = 100000
        if len(docs_text) > max_text_length:
            docs_text = docs_text[:max_text_length]
            print(f"[Admin Overview] Texto limitado a {max_text_length} caracteres")

        print(f"[Admin Overview] Longitud de docs_text: {len(docs_text)}")

        keywords = []
        technical_terms = []
        matching_terms = []

        if docs_text:
            try:
                keywords = [term for term, _ in top_terms(docs_text, limit=20)]
                print(f"[Admin Overview] Keywords extraídos: {len(keywords)}")

                known_names = set()
                for analysis in analyses:
                    results = analysis.get('results', {})
                    for fn in results.get('functions', []):
                        if fn.get('name'): known_names.add(fn['name'].lower())
                    for cls in results.get('classes', []):
                        if cls.get('name'): known_names.add(cls['name'].lower())
                    for ep in results.get('endpoints', []):
                        path = ep.get('path', '')
                        for token in re.findall(r'[A-Za-z_][A-Za-z0-9_]{3,}', path):
                            known_names.add(token.lower())

                print(f"[Admin Overview] Known names: {len(known_names)}")
                technical_terms = extract_technical_terms(docs_text, known_names=known_names, limit=20)
                print(f"[Admin Overview] Technical terms extraídos: {len(technical_terms)}")
                matching_terms = common_terms(keywords, technical_terms)
                print(f"[Admin Overview] Matching terms: {len(matching_terms)}")
            except Exception as e:
                print(f"[Admin Overview] Error en análisis de documentación: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[Admin Overview] No hay texto de documentación para analizar")

        print(f"[Admin Overview] Stats completas calculadas: keywords={len(keywords)}, technical={len(technical_terms)}, matching={len(matching_terms)}")

        return jsonify({
            "stats": {
                "total_users": total_users,
                "total_projects": total_projects,
                "completed_projects": completed_projects,
                "pending_projects": pending_projects,
                "errored_projects": errored_projects,
                "average_quality_score": average_quality,
                "language_distribution": language_distribution,
                "projects_per_month": projects_per_month,
                "total_documents": len(analyses)
            },
            "users": [
                {
                    "id": user['_id'],
                    "name": user.get('name'),
                    "email": user.get('email'),
                    "role": user.get('role', 'user'),
                    "created_at": user.get('created_at'),
                    "projects_count": user.get('projects_count', 0)
                }
                for user in users
            ],
            "projects": [],
            "data_analysis": {
                "keywords": keywords[:12],
                "technical_terms": technical_terms[:12],
                "matching_terms": matching_terms,
                "document_count": len(analyses)
            }
        }), 200
    except Exception as e:
        print(f"Error in admin_overview: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/classify-project/<project_id>', methods=['GET'])
@jwt_required()
@admin_required
def classify_project(project_id):
    """Clasifica un proyecto usando árbol de decisión entrenado con proyectos reales."""
    db = get_db()

    project = db.projects.find_one({"_id": project_id})
    if not project:
        return jsonify({"error": "Proyecto no encontrado"}), 404

    analysis = db.analysis_results.find_one({"project_id": project_id})
    if not analysis:
        return jsonify({"error": "No hay análisis disponible para este proyecto"}), 404

    results = analysis.get("results", {})
    if not results:
        return jsonify({"error": "El análisis no tiene resultados"}), 404

    try:
        from services.ml_analyzer import classify_project_type

        all_projects_data = _get_all_projects_data(db)  # 🆕 datos reales de todos los proyectos
        classification = classify_project_type(results, project, all_projects_data)

        return jsonify({
            "status": "ok",
            "classification": classification
        }), 200

    except Exception as e:
        print(f"Error en clasificación: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error al clasificar: {str(e)}"}), 500


@admin_bp.route('/classify-all-projects', methods=['GET'])
@jwt_required()
@admin_required
def classify_all_projects():
    """Clasifica todos los proyectos usando árbol de decisión entrenado con proyectos reales."""
    db = get_db()

    projects = list(db.projects.find({}))
    analyses = list(db.analysis_results.find({}))

    analysis_map = {}
    for analysis in analyses:
        project_id = analysis.get("project_id")
        if project_id:
            analysis_map[project_id] = analysis

    try:
        from services.ml_analyzer import classify_project_type

        all_projects_data = _get_all_projects_data(db)  # 🆕 se calcula UNA sola vez

        results = []
        for project in projects:
            project_id = project.get("_id")
            analysis = analysis_map.get(project_id)

            if analysis:
                results_data = analysis.get("results", {})
                if results_data:
                    try:
                        classification = classify_project_type(results_data, project, all_projects_data)
                        results.append({
                            "project_id": project_id,
                            "project_name": project.get("name", "Desconocido"),
                            "classification": classification
                        })
                    except Exception as e:
                        print(f"Error clasificando proyecto {project_id}: {e}")

        return jsonify({
            "status": "ok",
            "classifications": results
        }), 200

    except Exception as e:
        print(f"Error en classify_all_projects: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error al clasificar proyectos: {str(e)}"}), 500