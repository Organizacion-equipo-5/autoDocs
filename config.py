import os
from datetime import timedelta


class Config:
    SEND_FILE_MAX_AGE_DEFAULT = 0
    TEMPLATES_AUTO_RELOAD = True

    SECRET_KEY = os.environ.get(
        'SECRET_KEY',
        'autodocs-secret-key-change-in-production'
    )

    JWT_SECRET_KEY = os.environ.get(
        'JWT_SECRET_KEY',
        'jwt-secret-key-change-in-production'
    )

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

    # MongoDB
    MONGO_URI = os.environ.get(
        'MONGO_URI',
        'mongodb+srv://bri_db_user:hc087879@cluster.uvx8yek.mongodb.net/autodocs_ai?retryWrites=true&w=majority&appName=Cluster'
    )

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
    ENABLE_AI_ANALYSIS = os.environ.get('ENABLE_AI_ANALYSIS', 'false').lower() == 'true'
    MAX_ANALYSIS_FILES = int(os.environ.get('MAX_ANALYSIS_FILES', '300'))
    MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', '500000'))  # 500KB

    # Debug
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'