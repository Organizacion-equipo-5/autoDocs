"""
app/__init__.py
Application Factory — crea y configura la instancia de Flask.
"""
import logging
import os
from flask import Flask, jsonify, send_from_directory
from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from flask_cors import CORS

from app.config.settings import get_config
from app import db as db_manager

# Extensiones (inicializadas aquí, configuradas en create_app)
mongo_ext = PyMongo()
jwt = JWTManager()
mail = Mail()
bcrypt = Bcrypt()

logger = logging.getLogger(__name__)


def create_app(config_class=None):
    """Crea y retorna la aplicación Flask configurada."""
    # Configurar paths
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    frontend_path = os.path.join(basedir, 'frontend')
    
    app = Flask(
        __name__,
        static_folder=frontend_path,
        static_url_path=''
    )

    # ------------------------------------------------------------------ #
    # Configuración                                                        #
    # ------------------------------------------------------------------ #
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # ------------------------------------------------------------------ #
    # Extensiones                                                          #
    # ------------------------------------------------------------------ #
    mongo_ext.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Inyectar la instancia de mongo en el módulo de repositorios
    import app.repository.base_repository as base_repo
    base_repo.mongo = mongo_ext

    # Inyectar bcrypt en auth_service
    from app.services.auth_service import AuthService
    AuthService.__init__  # noqa — asegurar import

    # ------------------------------------------------------------------ #
    # Blueprints (rutas)                                                   #
    # ------------------------------------------------------------------ #
    from app.controllers import auth_bp, user_bp, med_bp, log_bp, iot_bp, notif_bp
    for bp in [auth_bp, user_bp, med_bp, log_bp, iot_bp, notif_bp]:
        app.register_blueprint(bp)

    # ------------------------------------------------------------------ #
    # Ruta de salud                                                        #
    # ------------------------------------------------------------------ #
    @app.get("/api/v1/health")
    def health():
        return jsonify({"status": "ok", "app": "MediTrack", "version": "1.0.0"})

    # ------------------------------------------------------------------ #
    # Servir Frontend (HTML/CSS/JS)                                       #
    # ------------------------------------------------------------------ #
    @app.route('/')
    def index():
        """Servir página principal del frontend"""
        return send_from_directory(frontend_path, 'index.html')
    
    @app.route('/<path:filename>')
    def serve_frontend(filename):
        """Servir archivos estáticos del frontend (CSS, JS, etc)"""
        return send_from_directory(frontend_path, filename)

    # ------------------------------------------------------------------ #
    # Conexión a MongoDB y Creación de BD/Colecciones                    #
    # ------------------------------------------------------------------ #
    with app.app_context():
        try:
            # Usar la función centralizada de conexión a MongoDB
            db_manager.connect_to_mongodb()
            logger.info("✅ MongoDB inicializado correctamente")
        except Exception as e:
            logger.error(f"⚠️  Error en inicialización de MongoDB: {e}")
        
        # Crear índices adicionales (backup si falla la conexión)
        _create_indexes(mongo_ext)

    # ------------------------------------------------------------------ #
    # Scheduler (solo en modo no-testing)                                  #
    # ------------------------------------------------------------------ #
    if not app.config.get("TESTING"):
        try:
            from app.utils.scheduler import init_scheduler
            init_scheduler(app)
        except ImportError as e:
            logger.warning(
                f"Scheduler no disponible: {e}. Continúa sin tareas programadas."
            )
        except Exception as e:
            logger.warning(f"No se pudo iniciar el scheduler: {e}")

    # ------------------------------------------------------------------ #
    # Manejadores de error globales                                        #
    # ------------------------------------------------------------------ #
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"ok": False, "error": "Recurso no encontrado"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"ok": False, "error": "Método no permitido"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception(e)
        return jsonify({"ok": False, "error": "Error interno del servidor"}), 500

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"ok": False, "error": "Token requerido", "detalle": reason}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"ok": False, "error": "Token inválido", "detalle": reason}), 422

    @jwt.expired_token_loader
    def expired_token(header, payload):
        return jsonify({"ok": False, "error": "Token expirado"}), 401

    return app


def _create_indexes(mongo_instance: PyMongo):
    """Crea índices de MongoDB para búsquedas frecuentes."""
    try:
        db = mongo_instance.db
        db.users.create_index("email", unique=True)
        db.users.create_index("rol")
        db.medications.create_index([("adulto_id", 1), ("activo", 1)])
        db.medication_logs.create_index([("adulto_id", 1), ("hora_programada", -1)])
        db.medication_logs.create_index([("medicamento_id", 1), ("hora_programada", -1)])
        db.iot_readings.create_index([("device_id", 1), ("timestamp", -1)])
        db.iot_readings.create_index([("adulto_id", 1), ("alerta", 1)])
        db.notifications.create_index([("destinatario_id", 1), ("leida", 1)])
        logger.info("Índices de MongoDB creados/verificados.")
    except Exception as e:
        logger.warning(f"No se pudieron crear índices: {e}")
