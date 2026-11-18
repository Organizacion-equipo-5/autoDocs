# routes/github_oauth.py
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import requests
from dotenv import load_dotenv
from flask import Blueprint, jsonify, make_response, redirect, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import generate_password_hash

from services.db import get_db

load_dotenv()

github_oauth_bp = Blueprint("github_oauth", __name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"
STATE_COOKIE = "gh_oauth_state"
STATE_TTL_MINUTES = 10


def _cfg():
    scope = os.getenv("GITHUB_OAUTH_SCOPE", "read:user user:email repo")
    scopes = scope.split()
    if "read:org" not in scopes:
        scopes.append("read:org")
    return {
        "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv(
            "GITHUB_REDIRECT_URI", "http://localhost:5000/api/github/callback"
        ),
        "scope": " ".join(scopes),
    }


def _gh_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "autoDocs",
    }


def _github_get_all_pages(url, token, params=None):
    results = []
    page = 1
    while True:
        query = dict(params or {})
        query.update({"per_page": 100, "page": page})
        response = requests.get(
            url,
            headers=_gh_headers(token),
            params=query,
            timeout=15,
        )
        if response.status_code != 200:
            return None, response
        page_results = response.json()
        if not isinstance(page_results, list):
            raise ValueError("GitHub devolvió una lista inválida.")
        results.extend(page_results)
        if len(page_results) < 100:
            return results, None
        page += 1


def _github_api_error(db, user_id, response, forbidden_message):
    if response.status_code == 401:
        db.users.update_one({"_id": user_id}, {"$unset": {"github": ""}})
        return jsonify({"error": "Tu conexión con GitHub expiró. Vuelve a conectarla."}), 401
    if response.status_code == 403:
        return jsonify({"error": forbidden_message}), 403
    return jsonify({"error": "GitHub devolvió un error"}), 502


def _json_for_script(value):
    """json.dumps seguro para incrustar dentro de un <script>."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _start_oauth(user_id=None):
    cfg = _cfg()
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise ValueError("GitHub OAuth no está configurado en el servidor")

    db = get_db()
    state = secrets.token_urlsafe(32)
    db.oauth_states.insert_one({
        "_id": state,
        "user_id": user_id,  # None = login, con valor = vincular cuenta
        "expires_at": (datetime.utcnow() + timedelta(minutes=STATE_TTL_MINUTES)).isoformat(),
    })
    params = urlencode({
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg["scope"],
        "state": state,
        "allow_signup": "true",
    })
    return state, f"{GITHUB_AUTHORIZE_URL}?{params}"


def _set_state_cookie(resp, state):
    resp.set_cookie(
        STATE_COOKIE, state,
        max_age=STATE_TTL_MINUTES * 60,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return resp


# 1) Iniciar sesión con GitHub (usuario aún no logueado)
@github_oauth_bp.route("/login", methods=["GET"])
def github_login():
    try:
        state, url = _start_oauth(user_id=None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    return _set_state_cookie(redirect(url), state)


# 2) Conectar GitHub desde el dashboard (usuario ya logueado con JWT)
@github_oauth_bp.route("/connect-url", methods=["POST"])
@jwt_required()
def github_connect_url():
    try:
        state, url = _start_oauth(user_id=get_jwt_identity())
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    return _set_state_cookie(make_response(jsonify({"url": url})), state)


# 3) Callback de GitHub
@github_oauth_bp.route("/callback", methods=["GET"])
def github_callback():
    db = get_db()
    code = request.args.get("code")
    state = request.args.get("state")

    def fail(msg, link_mode=False):
        dest = "/dashboard" if link_mode else "/"
        resp = redirect(f"{dest}?{urlencode({'github_error': msg})}")
        resp.delete_cookie(STATE_COOKIE)
        return resp

    if request.args.get("error"):
        return fail("Autorización cancelada")

    # Validar state: existe en BD, no expiró y coincide con la cookie
    record = db.oauth_states.find_one_and_delete({"_id": state}) if state else None
    cookie_state = request.cookies.get(STATE_COOKIE)
    if (
        not record
        or not cookie_state
        or not secrets.compare_digest(cookie_state, state)
        or datetime.utcnow() > datetime.fromisoformat(record["expires_at"])
    ):
        return fail("Estado inválido o expirado. Intenta de nuevo.")

    link_user_id = record.get("user_id")
    link_mode = bool(link_user_id)
    cfg = _cfg()

    try:
        token_res = requests.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
            },
            timeout=15,
        )
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        granted_scope = token_data.get("scope") or ""
        if not isinstance(granted_scope, str):
            return fail("GitHub devolvió permisos inválidos", link_mode)
        if not access_token:
            return fail("GitHub no entregó el token", link_mode)

        gh_user = requests.get(
            f"{GITHUB_API}/user", headers=_gh_headers(access_token), timeout=15
        ).json()
        if not gh_user.get("id"):
            return fail("No se pudo leer tu perfil de GitHub", link_mode)

        # Solo se usa un email verificado por GitHub
        email = None
        emails_res = requests.get(
            f"{GITHUB_API}/user/emails", headers=_gh_headers(access_token), timeout=15
        )
        if emails_res.status_code == 200:
            emails = emails_res.json()
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            any_verified = next((e for e in emails if e.get("verified")), None)
            email = (primary or any_verified or {}).get("email")
        email = (email or f"{gh_user['login']}@users.noreply.github.com").lower()
    except (requests.RequestException, ValueError):
        return fail("Error de conexión con GitHub", link_mode)

    github_data = {
        "id": gh_user["id"],
        "login": gh_user["login"],
        "avatar_url": gh_user.get("avatar_url", ""),
        "access_token": access_token,  # TODO: cifrar antes de guardar en producción
        "scope": granted_scope,
        "connected_at": datetime.utcnow().isoformat(),
    }

    # ---- Modo vincular: usuario ya logueado ----
    if link_mode:
        taken = db.users.find_one({"github.id": gh_user["id"], "_id": {"$ne": link_user_id}})
        if taken:
            return fail("Esa cuenta de GitHub ya está vinculada a otro usuario", True)
        db.users.update_one({"_id": link_user_id}, {"$set": {"github": github_data}})
        resp = redirect("/dashboard?github=connected")
        resp.delete_cookie(STATE_COOKIE)
        return resp

    # ---- Modo login: buscar o crear usuario ----
    user = db.users.find_one({"github.id": gh_user["id"]}) or db.users.find_one({"email": email})
    if user:
        db.users.update_one({"_id": user["_id"]}, {"$set": {"github": github_data}})
    else:
        user = {
            "_id": str(uuid.uuid4()),
            "name": gh_user.get("name") or gh_user["login"],
            "email": email,
            # Contraseña aleatoria: entra por GitHub (o por "olvidé mi contraseña")
            "password": generate_password_hash(secrets.token_urlsafe(32)),
            "created_at": datetime.utcnow().isoformat(),
            "plan": "free",
            "projects_count": 0,
            "role": "user",
            "github": github_data,
        }
        db.users.insert_one(user)

    jwt_token = create_access_token(identity=user["_id"])
    user_payload = {
        "id": user["_id"],
        "name": user.get("name"),
        "email": user["email"],
        "role": user.get("role", "user"),
    }
    dest = "/admin_dashboard" if user_payload["role"] == "admin" else "/dashboard"

    # Guarda token y user igual que handleLogin() y redirige
    html = (
        "<!doctype html><meta charset='utf-8'><title>Iniciando sesión…</title>"
        "<script>"
        f"localStorage.setItem('token', {_json_for_script(jwt_token)});"
        f"localStorage.setItem('user', {_json_for_script(json.dumps(user_payload))});"
        f"location.replace({_json_for_script(dest)});"
        "</script>"
    )
    resp = make_response(html)
    resp.delete_cookie(STATE_COOKIE)
    return resp


# 4) Estado, repos y desconexión
@github_oauth_bp.route("/status", methods=["GET"])
@jwt_required()
def github_status():
    user = get_db().users.find_one({"_id": get_jwt_identity()}, {"github": 1})
    gh = (user or {}).get("github")
    if not gh:
        return jsonify({"connected": False}), 200
    return jsonify({
        "connected": True,
        "login": gh.get("login"),
        "avatar_url": gh.get("avatar_url"),
        "organization_access": "read:org" in (gh.get("scope") or "").replace(",", " ").split(),
    }), 200


@github_oauth_bp.route("/repos", methods=["GET"])
@jwt_required()
def github_repos():
    db = get_db()
    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": user_id}, {"github": 1})
    token = ((user or {}).get("github") or {}).get("access_token")
    if not token:
        return jsonify({"error": "GitHub no conectado"}), 400

    try:
        repos, error_response = _github_get_all_pages(
            f"{GITHUB_API}/user/repos",
            token,
            {
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        if error_response:
            return _github_api_error(
                db,
                user_id,
                error_response,
                "GitHub no permitió acceder a tus repositorios. Revisa los permisos de la cuenta.",
            )

        organizations, error_response = _github_get_all_pages(
            f"{GITHUB_API}/user/orgs",
            token,
        )
        if error_response:
            return _github_api_error(
                db,
                user_id,
                error_response,
                "No se pudieron leer tus organizaciones. Vuelve a conectar GitHub para autorizar el permiso read:org.",
            )

        repos_by_name = {
            repo.get("full_name"): repo
            for repo in repos
            if isinstance(repo, dict) and isinstance(repo.get("full_name"), str)
        }
        for organization in organizations:
            login = organization.get("login") if isinstance(organization, dict) else None
            if not isinstance(login, str) or not login:
                continue
            organization_repos, error_response = _github_get_all_pages(
                f"{GITHUB_API}/orgs/{quote(login, safe='')}/repos",
                token,
                {"type": "all", "sort": "updated"},
            )
            if error_response:
                return _github_api_error(
                    db,
                    user_id,
                    error_response,
                    f"GitHub no permitió acceder a los repositorios de {login}. Revisa el acceso de la organización.",
                )
            for repo in organization_repos:
                if isinstance(repo, dict) and isinstance(repo.get("full_name"), str):
                    repos_by_name[repo["full_name"]] = repo
    except requests.RequestException:
        return jsonify({"error": "No se pudo conectar con GitHub"}), 502
    except ValueError as error:
        return jsonify({"error": str(error)}), 502

    return jsonify([
        {
            "full_name": r["full_name"],
            "name": r["name"],
            "private": r["private"],
            "html_url": r["html_url"],
            "description": r.get("description") or "",
            "default_branch": r.get("default_branch"),
        }
        for r in repos_by_name.values()
    ]), 200


@github_oauth_bp.route("/organizations", methods=["GET"])
@jwt_required()
def github_organizations():
    db = get_db()
    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": user_id}, {"github": 1})
    token = ((user or {}).get("github") or {}).get("access_token")
    if not token:
        return jsonify({"error": "GitHub no conectado"}), 400

    try:
        organizations, error_response = _github_get_all_pages(
            f"{GITHUB_API}/user/orgs",
            token,
        )
    except requests.RequestException:
        return jsonify({"error": "No se pudo conectar con GitHub"}), 502
    except ValueError as error:
        return jsonify({"error": str(error)}), 502

    if error_response:
        return _github_api_error(
            db,
            user_id,
            error_response,
            "No se pudieron leer tus organizaciones. Vuelve a conectar GitHub para autorizar el permiso read:org.",
        )

    return jsonify([
        {
            "login": organization["login"],
            "avatar_url": organization.get("avatar_url", ""),
            "html_url": f"https://github.com/{organization['login']}",
        }
        for organization in organizations
        if isinstance(organization, dict) and isinstance(organization.get("login"), str)
    ]), 200


@github_oauth_bp.route("/disconnect", methods=["POST"])
@jwt_required()
def github_disconnect():
    get_db().users.update_one({"_id": get_jwt_identity()}, {"$unset": {"github": ""}})
    return jsonify({"message": "GitHub desconectado"}), 200