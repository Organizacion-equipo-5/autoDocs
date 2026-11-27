import hashlib
import hmac
import logging
import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from routes.analysis import run_analysis_async
from services.analysis_history import diff_snapshots, resolve_pair
from services.ci_report import COMMENT_MARKER, render_pr_comment
from services.db import get_db
from services.file_handler import clone_github_repo
from services.github_client import extract_repo_info


github_bp = Blueprint("github_integration", __name__)
GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 10
_PROJECT_LOCKS = {}
_PROJECT_LOCKS_GUARD = threading.Lock()


def _project_lock(project_id):
    with _PROJECT_LOCKS_GUARD:
        return _PROJECT_LOCKS.setdefault(project_id, threading.Lock())


def _find_project_for_repo(db, owner, repo):
    for project in db.projects.find({"github_url": {"$exists": True, "$ne": ""}}):
        try:
            project_owner, project_repo = extract_repo_info(project.get("github_url", ""))
        except (AttributeError, TypeError, ValueError):
            continue
        if (project_owner.casefold(), project_repo.casefold()) == (owner.casefold(), repo.casefold()):
            return project
    return None


def _github_headers(token=None):
    headers = {"Accept": "application/vnd.github+json"}
    token = token or current_app.config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_unauthorized_response(db, user_id, github_token, error):
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) != 401:
        return None

    if github_token:
        db.users.update_one({"_id": user_id}, {"$unset": {"github": ""}})
        return jsonify({"error": "Tu conexión con GitHub expiró. Vuelve a conectarla."}), 401
    return jsonify({
        "error": "La credencial de GitHub configurada en el servidor no es válida."
    }), 502


def _github_branch_data(github_url, branch, etag=None, token=None):
    owner, repo = extract_repo_info(github_url)
    url = f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/branches/{quote(branch, safe='')}"
    headers = _github_headers(token)
    if etag:
        headers["If-None-Match"] = etag
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    if response.status_code == 304:
        return {"not_modified": True, "etag": etag}
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json()
    commit = data.get("commit") if isinstance(data, dict) else None
    sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
        raise ValueError("GitHub devolvió una revisión de rama inválida.")
    response_headers = getattr(response, "headers", {})
    return {
        "name": data.get("name", branch),
        "sha": sha,
        "etag": response_headers.get("ETag"),
    }


def _store_branch_etag(db, project_id, etag):
    if etag:
        db.projects.update_one(
            {"_id": project_id},
            {"$set": {"github_etag": etag}},
        )
    else:
        db.projects.update_one(
            {"_id": project_id},
            {"$unset": {"github_etag": ""}},
        )


def _queue_branch_analysis(db, project, branch, sha, event_type, force=False, etag=None):
    project_id = project["_id"]
    if project.get("status") == "analyzing":
        return "analyzing"
    if project.get("github_pending_sha") == sha:
        if project.get("github_branch") == branch:
            _store_branch_etag(db, project_id, etag)
        return "pending"
    if (
        not force
        and project.get("github_branch") == branch
        and project.get("github_sha") == sha
    ):
        _store_branch_etag(db, project_id, etag)
        return "unchanged"

    project_path = project.get("file_path")
    if not project_path or not Path(project_path).is_dir():
        try:
            project_path = clone_github_repo(project.get("github_url", ""), project_id)
        except Exception as error:
            raise ValueError(f"No se pudo recuperar el repositorio: {error}") from error
        if not Path(project_path).is_dir():
            raise ValueError("No se pudo recuperar el repositorio clonado del proyecto.")
        db.projects.update_one(
            {"_id": project_id},
            {"$set": {"file_path": project_path}},
        )
        project["file_path"] = project_path

    reservation_filter = {
        "_id": project_id,
        "status": {"$ne": "analyzing"},
        "github_pending_sha": {"$ne": sha},
    }
    if not force:
        reservation_filter["github_sha"] = {"$ne": sha}
    reservation_update = {
        "$set": {
            "github_branch": branch,
            "github_pending_sha": sha,
            "status": "pending",
        }
    }
    if etag:
        reservation_update["$set"]["github_etag"] = etag
    else:
        reservation_update["$unset"] = {"github_etag": ""}
    reservation = db.projects.update_one(reservation_filter, reservation_update)
    if not reservation.modified_count:
        return "pending"

    activity_id = hashlib.sha256(
        f"{project_id}:{event_type}:{branch}:{sha}".encode("utf-8")
    ).hexdigest()
    db.github_activity.update_one(
        {"_id": activity_id},
        {"$setOnInsert": {
            "_id": activity_id,
            "project_id": project_id,
            "event_type": event_type,
            "branch": branch,
            "kind": "commit",
            "sha": sha,
            "message": "Cambio detectado por sondeo" if event_type == "poll" else "Cambio de rama solicitado",
            "url": f"{project.get('github_url', '').rstrip('/')}/commit/{sha}",
            "occurred_at": datetime.utcnow().isoformat(),
            "received_at": datetime.utcnow().isoformat(),
            "status": "pending",
        }},
        upsert=True,
    )
    _start_activity_worker(db, project, branch, sha, event_type, [activity_id])
    return "queued"


def _process_github_activity(db, project, branch, pushed_sha, event_type, activity_ids):
    project_id = project["_id"]
    try:
        with _project_lock(project_id):
            project_path = project.get("file_path")
            if not project_path or not Path(project_path).is_dir():
                raise ValueError("No se encontró el repositorio clonado del proyecto.")

            ref_check = subprocess.run(
                ["git", "check-ref-format", "--branch", branch],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if ref_check.returncode:
                raise ValueError("GitHub envió un nombre de rama no válido.")

            remote_ref = f"refs/remotes/origin/{branch}"
            subprocess.run(
                ["git", "fetch", "origin", f"+refs/heads/{branch}:{remote_ref}"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            if pushed_sha:
                target_sha = pushed_sha
            else:
                target = subprocess.run(
                    ["git", "rev-parse", remote_ref],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
                target_sha = target.stdout.strip()

            if not re.fullmatch(r"[0-9a-fA-F]{40,64}", target_sha):
                raise ValueError("GitHub envió un identificador de commit no válido.")

            subprocess.run(
                ["git", "checkout", "-B", branch, target_sha],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            target_sha = head.stdout.strip()
            db.github_activity.update_many(
                {"_id": {"$in": activity_ids}},
                {"$set": {"sha": target_sha, "status": "analyzing"}},
            )

            existing_snapshot = db.analysis_snapshots.find_one({
                "project_id": project_id,
                "source.sha": target_sha,
            })
            if existing_snapshot:
                db.github_activity.update_many(
                    {"_id": {"$in": activity_ids}},
                    {"$set": {"status": "completed"}},
                )
                db.projects.update_one(
                    {"_id": project_id},
                    {"$set": {
                        "github_branch": branch,
                        "github_sha": target_sha,
                        "status": "completed",
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                     "$unset": {"github_pending_sha": ""}},
                )
                return

            run_analysis_async(
                project_id,
                project_path,
                db,
                source={
                    "event": event_type,
                    "branch": branch,
                    "sha": target_sha,
                    "label": f"{branch}@{target_sha[:7]}",
                },
            )
            latest = db.projects.find_one({"_id": project_id}, {"status": 1}) or {}
            status = "completed" if latest.get("status") == "completed" else "error"
            update = {"status": status}
            if status == "error":
                update["error"] = latest.get("error_message", "No se pudo completar el análisis.")
            if status == "completed":
                project_update = {
                    "$set": {"github_branch": branch, "github_sha": target_sha},
                    "$unset": {"github_pending_sha": ""},
                }
            else:
                project_update = {"$unset": {"github_pending_sha": ""}}
            db.projects.update_one({"_id": project_id}, project_update)
            db.github_activity.update_many(
                {"_id": {"$in": activity_ids}},
                {"$set": update},
            )
    except Exception as error:
        logging.getLogger(__name__).exception("GitHub branch analysis failed for project %s", project_id)
        db.projects.update_one(
            {"_id": project_id},
            {"$set": {"status": "error", "error_message": str(error)},
             "$unset": {"github_pending_sha": "", "github_etag": ""}},
        )
        db.github_activity.update_many(
            {"_id": {"$in": activity_ids}},
            {"$set": {"status": "error", "error": str(error)}},
        )


def _start_activity_worker(db, project, branch, pushed_sha, event_type, activity_ids):
    worker = threading.Thread(
        target=_process_github_activity,
        args=(db, project, branch, pushed_sha, event_type, activity_ids),
        daemon=True,
    )
    worker.start()


@github_bp.route("/projects/<project_id>/branches", methods=["GET"])
@jwt_required()
def get_project_branches(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if not project.get("github_url"):
        return jsonify({"error": "Este proyecto no tiene URL de GitHub asociada."}), 400

    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.get("plan", "free") == "free":
        return jsonify({"error": "La selección de ramas está disponible para planes de pago."}), 403

    try:
        github_token = (user.get("github") or {}).get("access_token")
        owner, repo = extract_repo_info(project["github_url"])
        repo_response = requests.get(
            f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
            headers=_github_headers(github_token),
            timeout=REQUEST_TIMEOUT,
        )
        if repo_response.status_code == 404:
            return jsonify({"error": "No se encontró el repositorio en GitHub."}), 404
        repo_response.raise_for_status()
        repo_data = repo_response.json()
        if not isinstance(repo_data, dict):
            raise ValueError("GitHub devolvió información inválida del repositorio.")
        default_branch = repo_data.get("default_branch")
        names = []
        page = 1
        while True:
            branches_response = requests.get(
                f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/branches",
                params={"per_page": 100, "page": page},
                headers=_github_headers(github_token),
                timeout=REQUEST_TIMEOUT,
            )
            branches_response.raise_for_status()
            branches = branches_response.json()
            if not isinstance(branches, list):
                raise ValueError("GitHub devolvió una lista de ramas inválida.")
            names.extend(
                item["name"]
                for item in branches
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
            if len(branches) < 100:
                break
            page += 1
        if default_branch and default_branch not in names:
            names.insert(0, default_branch)
        return jsonify({
            "branches": names,
            "selected": project.get("github_branch") or default_branch,
        }), 200
    except (requests.RequestException, ValueError) as error:
        auth_error = _github_unauthorized_response(db, user_id, github_token, error)
        if auth_error:
            return auth_error
        logging.getLogger(__name__).exception("Could not load branches for project %s", project_id)
        return jsonify({"error": f"No se pudieron cargar las ramas de GitHub: {error}"}), 502


@github_bp.route("/projects/<project_id>/branch", methods=["POST"])
@jwt_required()
def select_project_branch(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if not project.get("github_url"):
        return jsonify({"error": "Este proyecto no tiene URL de GitHub asociada."}), 400

    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.get("plan", "free") == "free":
        return jsonify({"error": "La selección de ramas está disponible para planes de pago."}), 403
    if project.get("status") == "analyzing":
        return jsonify({"error": "El proyecto ya se está analizando. Inténtalo de nuevo cuando termine."}), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe incluir la rama seleccionada."}), 400
    branch = data.get("branch")
    if not isinstance(branch, str) or not branch.strip() or len(branch) > 255:
        return jsonify({"error": "Debes seleccionar una rama válida."}), 400
    branch = branch.strip()

    try:
        github_token = (user.get("github") or {}).get("access_token")
        branch_data = _github_branch_data(project["github_url"], branch, token=github_token)
        if branch_data is None:
            return jsonify({"error": "La rama seleccionada no existe en GitHub."}), 404
        result = _queue_branch_analysis(
            db, project, branch, branch_data["sha"], "branch_switch",
            force=True, etag=branch_data.get("etag"),
        )
    except (requests.RequestException, ValueError) as error:
        auth_error = _github_unauthorized_response(db, user_id, github_token, error)
        if auth_error:
            return auth_error
        logging.getLogger(__name__).exception("Could not select branch for project %s", project_id)
        return jsonify({"error": f"No se pudo cambiar de rama: {error}"}), 502

    if result == "analyzing":
        return jsonify({"error": "El proyecto ya se está analizando. Inténtalo de nuevo cuando termine."}), 409
    return jsonify({
        "message": f"Rama '{branch}' seleccionada. El análisis comenzará pronto.",
        "branch": branch,
        "status": result,
    }), 202


@github_bp.route("/projects/<project_id>/poll", methods=["POST"])
@jwt_required()
def poll_project_branch(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    if not project.get("github_url"):
        return jsonify({"error": "Este proyecto no tiene URL de GitHub asociada."}), 400

    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.get("plan", "free") == "free":
        return jsonify({"error": "El sondeo de ramas está disponible para planes de pago."}), 403
    if project.get("status") == "analyzing":
        return jsonify({"status": "analyzing"}), 202

    try:
        github_token = (user.get("github") or {}).get("access_token")
        branch = project.get("github_branch")
        if not branch:
            owner, repo = extract_repo_info(project["github_url"])
            repo_response = requests.get(
                f"{GITHUB_API}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
                headers=_github_headers(github_token),
                timeout=REQUEST_TIMEOUT,
            )
            if repo_response.status_code == 404:
                return jsonify({"error": "No se encontró el repositorio en GitHub."}), 404
            repo_response.raise_for_status()
            repo_data = repo_response.json()
            branch = repo_data.get("default_branch") if isinstance(repo_data, dict) else None
            if not isinstance(branch, str) or not branch:
                raise ValueError("GitHub no indicó una rama principal para este repositorio.")

        branch_data = _github_branch_data(
            project["github_url"], branch, project.get("github_etag"), github_token
        )
        if branch_data is None:
            return jsonify({"error": f"La rama '{branch}' ya no existe en GitHub."}), 404
        if branch_data.get("not_modified"):
            return jsonify({"branch": branch, "status": "unchanged"}), 200
        _store_branch_etag(db, project_id, branch_data.get("etag"))
        if not project.get("github_sha") and project.get("file_path") and Path(project["file_path"]).is_dir():
            local_branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project["file_path"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
            if local_branch == branch:
                local_sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=project["file_path"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                ).stdout.strip()
                project["github_branch"] = branch
                project["github_sha"] = local_sha
                db.projects.update_one(
                    {"_id": project_id, "github_sha": {"$exists": False}},
                    {"$set": {"github_branch": branch, "github_sha": local_sha}},
                )

        result = _queue_branch_analysis(
            db, project, branch, branch_data["sha"], "poll",
            etag=branch_data.get("etag"),
        )
        return jsonify({"branch": branch, "status": result}), 202 if result == "queued" else 200
    except (requests.RequestException, subprocess.SubprocessError, ValueError) as error:
        auth_error = _github_unauthorized_response(db, user_id, github_token, error)
        if auth_error:
            return auth_error
        logging.getLogger(__name__).exception("Could not poll branch for project %s", project_id)
        return jsonify({"error": f"No se pudo revisar la rama de GitHub: {error}"}), 502


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


@github_bp.route("/webhook", methods=["POST"])
def github_webhook():
    secret = current_app.config.get("GITHUB_WEBHOOK_SECRET") or os.environ.get(
        "GITHUB_WEBHOOK_SECRET"
    )
    if not secret:
        return jsonify({"error": "La integración de webhooks de GitHub no está configurada."}), 503

    raw_body = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected_signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return jsonify({"error": "Firma de webhook inválida."}), 401

    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = request.get_json(silent=True)
    if not delivery_id or not isinstance(payload, dict):
        return jsonify({"error": "El webhook debe incluir un identificador y un objeto JSON."}), 400
    if event_type not in ("push", "create"):
        return jsonify({"accepted": True, "ignored": True}), 202

    repository = payload.get("repository") or {}
    if not isinstance(repository, dict):
        return jsonify({"error": "El repositorio del webhook no es válido."}), 400
    repository_url = repository.get("html_url") or ""
    if not repository_url and repository.get("full_name"):
        repository_url = f"https://github.com/{repository['full_name']}"
    if not isinstance(repository_url, str):
        return jsonify({"error": "La URL del repositorio del webhook no es válida."}), 400
    try:
        owner, repo = extract_repo_info(repository_url)
    except ValueError:
        return jsonify({"error": "No se pudo identificar el repositorio del webhook."}), 400

    if event_type == "push":
        ref = payload.get("ref", "")
        after = payload.get("after", "")
        if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
            return jsonify({"accepted": True, "ignored": True}), 202
        branch = ref[len("refs/heads/"):]
        if (
            not isinstance(after, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40,64}", after)
            or set(after) == {"0"}
        ):
            return jsonify({"accepted": True, "ignored": True}), 202
        commits = payload.get("commits") or []
        if not isinstance(commits, list):
            return jsonify({"error": "La lista de commits del webhook no es válida."}), 400
        commit_records = []
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            sha = commit.get("id") or commit.get("sha")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
                continue
            author = commit.get("author") or {}
            if not isinstance(author, dict):
                author = {}
            commit_records.append({
                "kind": "commit",
                "sha": sha,
                "message": str(commit.get("message") or ""),
                "author": str(author.get("name") or author.get("username") or ""),
                "url": f"{repository_url.rstrip('/')}/commit/{sha}",
                "occurred_at": commit.get("timestamp") or datetime.utcnow().isoformat(),
            })
        if not commit_records:
            head_commit = payload.get("head_commit") or {}
            author = head_commit.get("author") or {}
            if not isinstance(author, dict):
                author = {}
            commit_records.append({
                "kind": "commit",
                "sha": after,
                "message": str(head_commit.get("message") or ""),
                "author": str(author.get("name") or author.get("username") or ""),
                "url": f"{repository_url.rstrip('/')}/commit/{after}",
                "occurred_at": head_commit.get("timestamp") or datetime.utcnow().isoformat(),
            })
        pushed_sha = after
    else:
        if payload.get("ref_type") != "branch":
            return jsonify({"accepted": True, "ignored": True}), 202
        branch = payload.get("ref")
        if not isinstance(branch, str) or not branch:
            return jsonify({"error": "El nombre de la rama del webhook no es válido."}), 400
        sender = payload.get("sender") or {}
        if not isinstance(sender, dict):
            sender = {}
        commit_records = [{
            "kind": "branch",
            "sha": None,
            "message": "Rama creada",
            "author": str(sender.get("login") or ""),
            "url": f"{repository_url.rstrip('/')}/tree/{quote(branch, safe='')}",
            "occurred_at": datetime.utcnow().isoformat(),
        }]
        pushed_sha = None

    db = get_db()
    project = _find_project_for_repo(db, owner, repo)
    if not project:
        return jsonify({"error": "No hay un proyecto de AutoDocs asociado a este repositorio."}), 404
    if project.get("github_branch") and project["github_branch"] != branch:
        return jsonify({"accepted": True, "ignored": True, "reason": "branch_not_selected"}), 202

    delivery_key = hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()
    activity_ids = []
    for index, record in enumerate(commit_records):
        activity_id = f"{delivery_key}:{index}"
        activity = {
            "_id": activity_id,
            "project_id": project["_id"],
            "event_type": event_type,
            "branch": branch,
            **record,
            "status": "recorded",
            "received_at": datetime.utcnow().isoformat(),
        }
        result = db.github_activity.update_one(
            {"_id": activity_id},
            {"$setOnInsert": activity},
            upsert=True,
        )
        if result.upserted_id is not None:
            activity_ids.append(activity_id)

    if not activity_ids:
        return jsonify({"accepted": True, "duplicate": True}), 202

    db.github_activity.update_one(
        {"_id": activity_ids[-1]},
        {"$set": {"status": "pending"}},
    )
    _start_activity_worker(
        db, project, branch, pushed_sha, event_type, activity_ids
    )
    return jsonify({"accepted": True, "activities": len(activity_ids)}), 202
