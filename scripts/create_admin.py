import argparse
import sys
from pathlib import Path
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash

# Ensure the project root is on sys.path when running from scripts/create_admin.py
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from services.db import get_db


def create_admin_user(email: str, name: str, password: str):
    app = create_app()
    with app.app_context():
        db = get_db()
        existing = db.users.find_one({"email": email})

        if existing:
            db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {"role": "admin", "name": name}},
            )
            print(f"Usuario existente actualizado a admin: {email}")
            return existing["_id"]

        user = {
            "_id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "created_at": datetime.utcnow().isoformat(),
            "plan": "free",
            "projects_count": 0,
            "role": "admin",
        }
        db.users.insert_one(user)
        print(f"Administrador creado: {email}")
        return user["_id"]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Crea o actualiza un usuario administrador localmente.')
    parser.add_argument('--email', required=True, help='Email del administrador')
    parser.add_argument('--name', required=True, help='Nombre del administrador')
    parser.add_argument('--password', required=True, help='Contraseña del administrador')

    args = parser.parse_args()
    create_admin_user(args.email, args.name, args.password)
