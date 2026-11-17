import os

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from services.analysis_history import diff_snapshots, resolve_pair
from services.ci_report import COMMENT_MARKER, render_pr_comment
from services.db import get_db
from services.github_client import extract_repo_info


github_bp = Blueprint("github_integration", __name__)
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 10


@github_bp.route(
    "/projects/<project_id>/pull-requests/<int:pull_number>/report",
    methods=["POST"],
)
@jwt_required()
def publish_pull_request_report(project_id, pull_number):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    github_url = project.get("github_url")
    if not github_url:
        return jsonify({"error": "El proyecto no tiene una URL de GitHub asociada."}), 400

    try:
        owner, repo = extract_repo_info(github_url)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    if pull_number < 1:
        return jsonify({"error": "El número de pull request debe ser positivo."}), 400

    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400

    try:
        base, head = resolve_pair(
            db, project_id, data.get("from"), data.get("to")
        )
    except LookupError as error:
        return jsonify({"error": str(error)}), 404

    token = current_app.config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return jsonify({"error": "La integración de GitHub no está configurada."}), 503

    repository_api = f"{GITHUB_API}/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        pull_response = requests.get(
            f"{repository_api}/pulls/{pull_number}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if pull_response.status_code == 404:
            return jsonify({"error": "No se encontró el pull request en GitHub."}), 404
        pull_response.raise_for_status()

        user_response = requests.get(
            f"{GITHUB_API}/user", headers=headers, timeout=REQUEST_TIMEOUT
        )
        user_response.raise_for_status()
        user_data = user_response.json()
        if not isinstance(user_data, dict) or not user_data.get("login"):
            return jsonify({"error": "GitHub no devolvió la cuenta asociada al token."}), 502
        github_login = user_data["login"]

        comments_response = requests.get(
            f"{repository_api}/issues/{pull_number}/comments",
            headers=headers,
            params={"per_page": 100},
            timeout=REQUEST_TIMEOUT,
        )
        comments_response.raise_for_status()
        comments = comments_response.json()
        if not isinstance(comments, list):
            return jsonify({"error": "GitHub devolvió una respuesta de comentarios inválida."}), 502

        diff = diff_snapshots(base, head)
        report = render_pr_comment(diff, head, base)
        existing = next(
            (
                comment for comment in comments
                if isinstance(comment, dict)
                and (comment.get("user") or {}).get("login") == github_login
                and COMMENT_MARKER in (comment.get("body") or "")
            ),
            None,
        )
        if existing:
            response = requests.patch(
                f"{repository_api}/issues/comments/{existing['id']}",
                headers=headers,
                json={"body": report},
                timeout=REQUEST_TIMEOUT,
            )
            action = "updated"
        else:
            response = requests.post(
                f"{repository_api}/issues/{pull_number}/comments",
                headers=headers,
                json={"body": report},
                timeout=REQUEST_TIMEOUT,
            )
            action = "created"
        response.raise_for_status()
    except requests.exceptions.RequestException:
        current_app.logger.exception("GitHub report publishing request failed")
        return jsonify({"error": "No se pudo publicar el informe en GitHub."}), 502

    result = response.json()
    if not isinstance(result, dict):
        return jsonify({"error": "GitHub devolvió una respuesta de comentario inválida."}), 502
    return jsonify({
        "action": action,
        "comment_url": result.get("html_url"),
    }), 200 if action == "updated" else 201
