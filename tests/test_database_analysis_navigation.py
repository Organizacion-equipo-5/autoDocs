from flask import Flask

from routes.web import web_bp


def test_new_project_route_opens_dashboard_upload_modal():
    app = Flask(__name__, template_folder="../templates")
    app.register_blueprint(web_bp)
    client = app.test_client()

    response = client.get("/new-project")

    assert response.status_code == 302
    assert response.location.endswith("/dashboard?newProject=1")

    dashboard = client.get(response.location)
    assert dashboard.status_code == 200
    assert b"p.get('newProject') === '1'" in dashboard.data


def test_settings_route_redirects_to_profile_page():
    app = Flask(__name__, template_folder="../templates")
    app.register_blueprint(web_bp)
    client = app.test_client()

    response = client.get("/settings")

    assert response.status_code == 302
    assert response.location.endswith("/perfil")
    assert client.get(response.location).status_code == 200
