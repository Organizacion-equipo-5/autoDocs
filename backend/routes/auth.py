from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from services.db import get_db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

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
        "plan": "free",
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
