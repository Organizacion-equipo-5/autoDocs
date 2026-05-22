from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from functools import wraps
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
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    text = re.sub(r'`[^`]*`', ' ', text)
    text = re.sub(r'\[.*?\]\(.*?\)', ' ', text)
    text = re.sub(r'[^a-z0-9_\s]', ' ', text.lower())
    return text


def top_terms(text: str, limit=12):
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


@admin_bp.route('/overview', methods=['GET'])
@jwt_required()
@admin_required
def admin_overview():
    db = get_db()

    users = list(db.users.find({}, {"password": 0}))
    projects = list(db.projects.find({}, {"_id": 1, "name": 1, "user_id": 1, "language": 1, "status": 1, "created_at": 1, "stats": 1}))
    analyses = list(db.analysis_results.find({}, {"project_id": 1, "results": 1, "documentation": 1}))

    total_users = len(users)
    total_projects = len(projects)
    completed_projects = sum(1 for p in projects if p.get('status') == 'completed')
    pending_projects = sum(1 for p in projects if p.get('status') == 'pending')
    errored_projects = sum(1 for p in projects if p.get('status') == 'error')
    quality_scores = [p.get('stats', {}).get('quality_score', 0) for p in projects if p.get('stats', {}).get('quality_score') is not None]
    average_quality = round(sum(quality_scores) / max(len(quality_scores), 1), 1) if quality_scores else 0

    language_counts = {}
    for p in projects:
        lang = (p.get('language') or 'unknown').lower()
        language_counts[lang] = language_counts.get(lang, 0) + 1

    docs_text = ' '.join([analysis.get('documentation', '') for analysis in analyses if analysis.get('documentation')])
    keywords = [term for term, _ in top_terms(docs_text, limit=20)]

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

    technical_terms = extract_technical_terms(docs_text, known_names=known_names, limit=20)
    matching_terms = common_terms(keywords, technical_terms)

    user_map = {user['_id']: user for user in users}
    projects_with_user = [
        {
            "id": p['_id'],
            "name": p.get('name', 'Sin nombre'),
            "language": p.get('language', 'unknown'),
            "status": p.get('status', 'pending'),
            "quality_score": p.get('stats', {}).get('quality_score', 0),
            "owner": user_map.get(p.get('user_id'), {}).get('name', 'Desconocido'),
            "created_at": p.get('created_at')
        }
        for p in projects
    ]

    return jsonify({
        "stats": {
            "total_users": total_users,
            "total_projects": total_projects,
            "completed_projects": completed_projects,
            "pending_projects": pending_projects,
            "errored_projects": errored_projects,
            "average_quality_score": average_quality,
            "language_distribution": language_counts,
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
        "projects": projects_with_user,
        "data_analysis": {
            "keywords": keywords[:12],
            "technical_terms": technical_terms[:12],
            "matching_terms": matching_terms,
            "document_count": len(analyses)
        }
    }), 200
