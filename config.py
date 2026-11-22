import os
import secrets
from datetime import timedelta


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


_DEBUG = _env_bool('FLASK_DEBUG', False)


def _secret(name):
    """Lee un secreto del entorno. Nunca hay valores por defecto incrustados en el codigo.

    En produccion (FLASK_DEBUG apagado) es obligatorio definirlo. En desarrollo se genera
    uno aleatorio por proceso para no dejar una clave conocida en el repositorio.
    """
    value = os.environ.get(name)
    if value:
        return value
    if _DEBUG or os.environ.get('PYTEST_CURRENT_TEST') or os.environ.get('TESTING'):
        return secrets.token_urlsafe(48)
    raise RuntimeError(
        f'Falta la variable de entorno {name}. Defínela en .env o en el entorno del despliegue.'
    )


class Config:
    TEMPLATES_AUTO_RELOAD = _DEBUG

    SECRET_KEY = _secret('SECRET_KEY')

    JWT_SECRET_KEY = _secret('JWT_SECRET_KEY')

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    # MongoDB
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/autodocs_ai')

    # PayPal
    PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
    GITHUB_WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET')

    # Upload settings
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', './uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max
    ALLOWED_EXTENSIONS = {
        'zip', 'tar', 'gz', 'py', 'js', 'ts',
        'java', 'php', 'go', 'rb', 'cs'
    }

    # Export settings
    EXPORT_FOLDER = os.environ.get('EXPORT_FOLDER', './exports')

    # Performance settings
    ENABLE_AI_ANALYSIS = os.environ.get('ENABLE_AI_ANALYSIS', 'true').lower() == 'true'
    MAX_ANALYSIS_FILES = int(os.environ.get('MAX_ANALYSIS_FILES', '300'))
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '500000'))  # 500KB

    # Debug
    DEBUG = _DEBUG

    # Orígenes permitidos para CORS en /api/* (separados por coma).
    # Si no se define, se permite cualquier origen ("*") para no bloquear al frontend.
    _cors_raw = os.environ.get('CORS_ORIGINS', '').strip()
    CORS_ORIGINS = (
        [o.strip() for o in _cors_raw.split(',') if o.strip()]
        if _cors_raw
        else ["*"]
    )