from pymongo import MongoClient
from flask import current_app, g

def get_db():
    if 'db' not in g:
        client = MongoClient(current_app.config['MONGO_URI'])
        g.db = client.get_default_database()
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.client.close()

def init_db_indexes(app):
    with app.app_context():
        db = get_db()
        # Índices existentes
        db.users.create_index("email", unique=True)
        db.projects.create_index("user_id")
        db.analysis_results.create_index("project_id")
        db.password_reset_codes.create_index([("email", 1), ("code", 1)], unique=True)
        db.password_reset_codes.create_index("expires_at")
        
        # NUEVO: Índices para usage_logs
        db.usage_logs.create_index([("user_id", 1), ("action", 1), ("created_at", 1)])
        db.usage_logs.create_index([("user_id", 1), ("created_at", -1)])
        db.usage_logs.create_index("created_at")
        
        print(" Todos los índices creados/verificados")