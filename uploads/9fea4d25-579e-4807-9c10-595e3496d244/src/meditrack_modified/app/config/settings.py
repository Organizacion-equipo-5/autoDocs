"""
app/config/settings.py
Configuración centralizada de la aplicación por entorno.
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class BaseConfig:
    """Configuración base compartida por todos los entornos."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JSON_SORT_KEYS = False

    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/meditrack")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "meditrack")

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 604800))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # Correo
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "MediTrack <noreply@meditrack.com>")

    # Paginación
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", 20))

    # IoT (stub para implementación futura)
    IOT_ENABLED = os.getenv("IOT_ENABLED", "False") == "True"
    IOT_BROKER_HOST = os.getenv("IOT_BROKER_HOST", "localhost")
    IOT_BROKER_PORT = int(os.getenv("IOT_BROKER_PORT", 1883))
    IOT_BROKER_USER = os.getenv("IOT_BROKER_USER", "")
    IOT_BROKER_PASSWORD = os.getenv("IOT_BROKER_PASSWORD", "")
    IOT_TOPIC_PREFIX = os.getenv("IOT_TOPIC_PREFIX", "meditrack/devices")

    # Notificaciones Push (stub)
    FCM_ENABLED = os.getenv("FCM_ENABLED", "False") == "True"
    FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "")

    # Roles del sistema
    ROLES = {
        "admin": "Administrador del sistema",
        "adulto": "Adulto mayor (paciente)",
        "familiar": "Familiar o cuidador",
        "medico": "Médico tratante",
    }
    VALID_ROLES = list(ROLES.keys())
    DEFAULT_ROLE = "adulto"


class DevelopmentConfig(BaseConfig):
    FLASK_ENV = "development"
    DEBUG = True
    TESTING = False


class TestingConfig(BaseConfig):
    FLASK_ENV = "testing"
    DEBUG = True
    TESTING = True
    MONGO_URI = os.getenv("MONGO_URI_TEST", "mongodb://localhost:27017/meditrack_test")
    MONGO_DB_NAME = "meditrack_test"


class ProductionConfig(BaseConfig):
    FLASK_ENV = "production"
    DEBUG = False
    TESTING = False


_config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.getenv("FLASK_ENV", "development")
    return _config_map.get(env, DevelopmentConfig)
