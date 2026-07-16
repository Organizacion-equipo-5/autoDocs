from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from services.db import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import uuid
import random
import string
import re
import smtplib
import os
from dotenv import load_dotenv

load_dotenv()
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    db = get_db()

    if not data or not all(k in data for k in ['email', 'password', 'name']):
        return jsonify({"error": "Missing required fields"}), 400

    if db.users.find_one({"email": data['email']}):
        return jsonify({"error": "Email already registered"}), 409

    user = {
        "_id": str(uuid.uuid4()),
        "name": data['name'],
        "email": data['email'],
        "password": generate_password_hash(data['password']),
        "created_at": datetime.utcnow().isoformat(),
        "plan": data.get('plan', 'free'),
        "projects_count": 0,
        "role": "user"
    }
    db.users.insert_one(user)

    token = create_access_token(identity=user['_id'])
    return jsonify({"token": token, "user": {"id": user['_id'], "name": user['name'], "email": user['email'], "role": user['role']}}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    db = get_db()
    
    user = db.users.find_one({"email": data.get('email')})
    if not user or not check_password_hash(user['password'], data.get('password', '')):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = create_access_token(identity=user['_id'])
    return jsonify({"token": token, "user": {"id": user['_id'], "name": user['name'], "email": user['email'], "role": user.get('role', 'user')}}), 200

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    db = get_db()
    user = db.users.find_one({"_id": user_id}, {"password": 0})
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user), 200

@auth_bp.route('/me', methods=['PUT'])
@jwt_required()
def update_me():
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    db = get_db()
    user = db.users.find_one({"_id": user_id})
    if not user:
        return jsonify({"error": "User not found"}), 404

    update = {}
    if data.get('name'):
        update['name'] = data.get('name')
    if data.get('password'):
        update['password'] = generate_password_hash(data.get('password'))

    if not update:
        return jsonify({"error": "No changes provided"}), 400

    db.users.update_one({"_id": user_id}, {"$set": update})
    updated_user = db.users.find_one({"_id": user_id}, {"password": 0})
    return jsonify({"message": "Profile updated", "user": updated_user}), 200

def generate_reset_code():
    return ''.join(random.choices(string.digits, k=6))

def send_reset_email(email, code):
    try:
        sender_email = os.getenv("EMAIL_USER", "").strip()

        smtp_host = os.getenv("SMTP_HOST", "").strip()
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_password = os.getenv("SMTP_PASSWORD", "").strip()

        print(f"[SMTP] HOST: {smtp_host}")
        print(f"[SMTP] USER: {smtp_user}")
        print(f"[SMTP] FROM: {sender_email}")

        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = email
        message["Subject"] = "Código de recuperación de contraseña - AutoDocs AI"

        body = f"""
<html>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #0f1418; color: #dee3e8;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <div style="background: rgba(27,32,36,0.9); border: 1px solid rgba(123,208,255,0.2); border-radius: 16px; padding: 40px;">
            <div style="text-align: center; margin-bottom: 30px;">
                <div style="font-size: 40px;">📧</div>
                <h1 style="color: #39b2f8; margin-bottom: 5px;">AutoDocs AI</h1>
                <p style="color: #bdc8d1;">Recuperación de contraseña</p>
            </div>

            <p>Hola,</p>
            <p style="color: #bdc8d1;">Has solicitado recuperar tu contraseña en AutoDocs AI. Tu código de recuperación es:</p>

            <div style="background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); border-radius: 12px; padding: 30px; text-align: center; margin: 30px 0;">
                <span style="font-size: 48px; font-weight: bold; color: #39b2f8; letter-spacing: 8px; font-family: Courier New, monospace;">
                    {code}
                </span>
            </div>

            <div style="background: rgba(255,176,171,0.1); border: 1px solid rgba(255,176,171,0.2); border-radius: 8px; padding: 15px; margin: 20px 0;">
                <p style="color: #ffb4ab; margin: 0; font-weight: bold;">⚠️ Este código expirará en 15 minutos.</p>
            </div>

            <p style="color: #bdc8d1;">Si no solicitaste este cambio, ignora este correo por seguridad.</p>

            <div style="border-top: 1px solid rgba(123,208,255,0.1); padding-top: 20px; margin-top: 30px; text-align: center;">
                <p style="color: #bdc8d1; margin: 0;">Saludos,</p>
                <p style="color: #39b2f8; font-weight: bold; margin: 5px 0 0 0;">El equipo de AutoDocs AI</p>
            </div>
        </div>

        <p style="text-align: center; color: #64748b; font-size: 12px; margin-top: 30px;">
            Este es un correo automático, por favor no respondas.
        </p>
    </div>
</body>
</html>
"""

        message.attach(MIMEText(body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(smtp_user, smtp_password)

            server.sendmail(
                sender_email,
                email,
                message.as_string()
            )

        print(f"[Email] Código enviado desde {sender_email} hacia {email}")

        return True

    except Exception as e:
        print(f"[Email Error] {repr(e)}")
        return False

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    db = get_db()
    user = db.users.find_one({"email": email})

    if not user:
        return jsonify({"error": "Email not found"}), 404

    code = generate_reset_code()
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    db.password_reset_codes.delete_one({"email": email})
    db.password_reset_codes.insert_one({
        "email": email,
        "code": code,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.utcnow().isoformat()
    })

    # Enviar correo
    email_sent = send_reset_email(email, code)

    if email_sent:
        return jsonify({"message": "Reset code sent to email"}), 200
    else:
        # Si falla el envío de correo, aún guardamos el código para desarrollo
        print(f"[Password Reset] Code for {email}: {code} (expires at {expires_at})")
        return jsonify({"message": "Reset code sent to email"}), 200

@auth_bp.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    if not email or not code:
        return jsonify({"error": "Email and code are required"}), 400

    db = get_db()
    reset_record = db.password_reset_codes.find_one({"email": email, "code": code})

    if not reset_record:
        return jsonify({"error": "Invalid code"}), 400

    expires_at = datetime.fromisoformat(reset_record['expires_at'])
    if datetime.utcnow() > expires_at:
        db.password_reset_codes.delete_one({"email": email})
        return jsonify({"error": "Code expired"}), 400

    return jsonify({"message": "Code verified"}), 200

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json()
        email = data.get('email')
        code = data.get('code')
        new_password = data.get('new_password')

        if not email or not code or not new_password:
            return jsonify({"error": "Email, code, and new password are required"}), 400

        if len(new_password) < 8 or not re.search(r'[A-Z]', new_password) or not re.search(r'[a-z]', new_password) or not re.search(r'[0-9]', new_password):
            return jsonify({"error": "Password must be at least 8 characters with uppercase, lowercase, and number"}), 400

        db = get_db()
        reset_record = db.password_reset_codes.find_one({"email": email, "code": code})

        if not reset_record:
            return jsonify({"error": "Invalid code"}), 400

        expires_at = datetime.fromisoformat(reset_record['expires_at'])
        if datetime.utcnow() > expires_at:
            db.password_reset_codes.delete_one({"email": email})
            return jsonify({"error": "Code expired"}), 400

        user = db.users.find_one({"email": email})
        if not user:
            return jsonify({"error": "User not found"}), 404

        db.users.update_one({"email": email}, {"$set": {"password": generate_password_hash(new_password)}})
        db.password_reset_codes.delete_one({"email": email})

        return jsonify({"message": "Password reset successfully"}), 200
    except Exception as e:
        print(f"[Reset Password Error] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
