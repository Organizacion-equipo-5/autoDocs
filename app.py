import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from routes.payments import payments_bp
from routes.plan_recommendation import plan_recommendation_bp
from services.db import init_db_indexes
from routes.github_oauth import github_oauth_bp

def create_app():
    app = Flask(__name__)

    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    JWTManager(app)

    from routes.auth import auth_bp
    from routes.projects import projects_bp
    from routes.analysis import analysis_bp
    from routes.export import export_bp
    from routes.web import web_bp
    from routes.admin import admin_bp
    from routes.insights import insights_bp
    from routes.github_integration import github_bp
    from routes.chat import chat_bp
    app.register_blueprint(github_oauth_bp, url_prefix='/api/github')

    app.register_blueprint(payments_bp, url_prefix='/api/payments')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(projects_bp, url_prefix='/api/projects')
    app.register_blueprint(analysis_bp, url_prefix='/api/analysis')
    app.register_blueprint(export_bp, url_prefix='/api/export')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(plan_recommendation_bp, url_prefix='/api/plan-recommendation')
    app.register_blueprint(insights_bp, url_prefix='/api/insights')
    app.register_blueprint(github_bp, url_prefix='/api/integrations/github')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(web_bp)

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Resource not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    # Inicializar índices de la base de datos (incluyendo usage_logs)
    try:
        init_db_indexes(app)
    except Exception:
        pass

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(
        debug=True,
        use_reloader=False,
        host="0.0.0.0",
        port=5000
    )