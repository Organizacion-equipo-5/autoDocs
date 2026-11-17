"""
routes/github_integration.py

Webhook de GitHub: regenera la documentación de un proyecto cada vez que alguien
hace push a la rama principal del repositorio con el que se creó.

Configuración
-------------
1. Define la variable de entorno GITHUB_WEBHOOK_SECRET (un secreto largo y aleatorio).
2. En GitHub: Settings → Webhooks → Add webhook
   - Payload URL:  https://TU-SERVIDOR/api/integrations/github/webhook
   - Content type: application/json
   - Secret:       el mismo valor de GITHUB_WEBHOOK_SECRET
   - Events:       "Just the push event"

Cada petición se valida con la firma HMAC-SHA256 (X-Hub-Signature-256). Si el secreto
no está configurado el endpoint responde 503 y no procesa nada.

Nota: el comentario con el cambio del score en los PR lo hace la GitHub Action
(ver action.yml y docs/GITHUB_INTEGRATION.md), porque corre dentro del repositorio.
"""
import hmac
import hashlib
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from services.db import get_db

github_bp = Blueprint('github_integration', __name__)

_BRANCH_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/\-]*$')
# owner: alfanumérico y guiones (sin empezar por punto/guion); repo: no puede ser "." ni ".."
_REPO_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-]*/(?!\.{1,2}$)[A-Za-z0-9_.\-]+$')
GIT_TIMEOUT = 180


def verify_signature(secret: str, body: bytes, header: str) -> bool:
    """Comprueba la firma X-Hub-Signature-256 en tiempo constante."""
    if not secret or not header or not header.startswith('sha256='):
        return False
    expected = 'sha256=' + hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def find_projects(db, full_name: str) -> list:
    """Proyectos creados desde el repositorio `owner/name` (sin distinguir mayúsculas ni .git)."""
    pattern = r'github\.com[/:]' + re.escape(full_name) + r'(?:\.git)?/?$'
    return list(db.projects.find({"github_url": {"$regex": pattern, "$options": "i"}}))


def _quota_exceeded(db, user_id) -> bool:
    """Misma regla de límite mensual que /api/analysis/<id>/start."""
    from routes.payments import PLANS
    user = db.users.find_one({"_id": user_id}) or {}
    limit = PLANS.get(user.get('plan', 'free'), PLANS['free']).get('analyses_per_month', -1)
    if limit == -1:
        return False
    start_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    ids = [p['_id'] for p in db.projects.find({"user_id": user_id}, {"_id": 1})]
    used = db.analysis_results.count_documents(
        {"project_id": {"$in": ids}, "created_at": {"$gte": start_month}}) if ids else 0
    return used >= limit


def _git(args, timeout=GIT_TIMEOUT):
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True, timeout=timeout)


def _sync_repository(project: dict, branch: str) -> str:
    """Actualiza (o clona) el repositorio del proyecto y devuelve su ruta."""
    from services.file_handler import clone_github_repo

    path = Path(project.get('file_path') or '')
    if path.is_dir() and (path / '.git').is_dir():
        _git(['-C', str(path), 'fetch', 'origin', branch])
        _git(['-C', str(path), 'reset', '--hard', 'FETCH_HEAD'])
        return str(path.resolve())
    candidate = Path('uploads') / str(project['_id'])
    if not candidate.exists() or not any(candidate.iterdir()):
        return clone_github_repo(project['github_url'], project['_id'])
    raise RuntimeError("El código del proyecto no es un clon de git; vuelve a crear el proyecto desde la URL.")


def _regenerate(db, project: dict, branch: str, source: dict):
    from routes.analysis import run_analysis_async
    project_id = project['_id']
    try:
        db.projects.update_one({"_id": project_id}, {"$set": {
            "status": "analyzing", "updated_at": datetime.utcnow().isoformat()}})
        path = _sync_repository(project, branch)
        run_analysis_async(project_id, path, db, source=source)
    except Exception as e:  # noqa: BLE001 - el hilo nunca debe morir en silencio
        db.projects.update_one({"_id": project_id}, {"$set": {
            "status": "error", "error_message": f"No se pudo actualizar desde GitHub: {e}",
            "updated_at": datetime.utcnow().isoformat()}})


@github_bp.route('/webhook', methods=['POST'])
def webhook():
    secret = os.environ.get('GITHUB_WEBHOOK_SECRET', '')
    if not secret:
        return jsonify({"error": "Webhook no configurado en el servidor"}), 503

    body = request.get_data()
    if not verify_signature(secret, body, request.headers.get('X-Hub-Signature-256', '')):
        return jsonify({"error": "Firma inválida"}), 401

    event = request.headers.get('X-GitHub-Event', '')
    if event == 'ping':
        return jsonify({"message": "pong"}), 200
    if event != 'push':
        return jsonify({"message": f"Evento '{event}' ignorado"}), 202

    payload = request.get_json(silent=True) or {}
    repo = payload.get('repository') or {}
    full_name = repo.get('full_name', '')
    default_branch = repo.get('default_branch', '')
    ref = payload.get('ref', '')

    if not _REPO_RE.match(full_name) or not _BRANCH_RE.match(default_branch):
        return jsonify({"error": "Payload inválido"}), 400
    if payload.get('deleted') or ref != f'refs/heads/{default_branch}':
        return jsonify({"message": "Solo se procesan pushes a la rama principal"}), 202

    head = payload.get('head_commit') or {}
    source = {
        "event": "push", "sha": payload.get('after', ''), "branch": default_branch,
        "message": (head.get('message') or '').splitlines()[0] if head.get('message') else '',
        "repo": full_name, "actor": (payload.get('pusher') or {}).get('name', ''),
    }

    db = get_db()
    started, skipped = [], []
    for project in find_projects(db, full_name):
        if project.get('status') == 'analyzing':
            skipped.append({"project_id": project['_id'], "reason": "ya se está analizando"})
        elif _quota_exceeded(db, project.get('user_id')):
            skipped.append({"project_id": project['_id'], "reason": "límite mensual del plan alcanzado"})
        else:
            threading.Thread(target=_regenerate, args=(db, project, default_branch, source),
                             daemon=True).start()
            started.append(project['_id'])

    return jsonify({"message": "Push recibido", "started": started, "skipped": skipped}), 202
