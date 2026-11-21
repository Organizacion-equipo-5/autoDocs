import os
from datetime import timedelta

# ── Development defaults ────────────────────────────────────────────────────
# Override ALL of these via environment variables or a .env file in production.
# Never commit real credentials to source control.
_DEV_SECRET      = 'autodocs-dev-secret-change-in-production'
_DEV_JWT_SECRET  = 'jwt-dev-secret-change-in-production'
# Use MONGO_URI in .env/deployment. In local development this falls back
# to a local MongoDB instance instead of embedding a shared credential.
_DEV_MONGO_URI = 'mongodb://localhost:27017/autodocs_ai'


class Config:
    SEND_FILE_MAX_AGE_DEFAULT = 0
    TEMPLATES_AUTO_RELOAD = True

    # In production set SECRET_KEY and JWT_SECRET_KEY to long random strings.
    SECRET_KEY     = os.environ.get('SECRET_KEY',     _DEV_SECRET)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', _DEV_JWT_SECRET)

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    # MongoDB
    MONGO_URI = os.environ.get('MONGO_URI', _DEV_MONGO_URI)

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

    # Debug – off by default; enable explicitly with FLASK_DEBUG=true
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')