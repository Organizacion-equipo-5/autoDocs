from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.analyzer import ProjectAnalyzer
from services.doc_generator import DocGenerator
from datetime import datetime
import threading

analysis_bp = Blueprint('analysis', __name__)


def run_analysis_async(project_id, project_path, db):
    """
    Ejecuta el análisis en segundo plano.

    1. Marca el proyecto como "analyzing".
    2. Analiza el código con ProjectAnalyzer.
    3. Genera documentación con DocGenerator.
    4. Guarda los resultados en la base de datos.
    5. Actualiza el estado del proyecto a "completed" o "error".
    """
    try:
        # Validar que project_path existe antes de iniciar.
        if not project_path:
            raise ValueError("No se proporcionó una ruta de proyecto válida. Debes subir un archivo o proporcionar una URL de GitHub.")

        # Marca el proyecto como en proceso de análisis.
        db.projects.update_one({"_id": project_id}, {"$set": {"status": "analyzing"}})

        # Analiza el proyecto y extrae métricas y estructura.
        analyzer = ProjectAnalyzer(project_path)
        results = analyzer.analyze()

        # Convierte esos resultados en documentación técnica.
        doc_gen = DocGenerator(results)
        documentation = doc_gen.generate()

        # Guarda resultados y documentación en la colección de análisis.
        db.analysis_results.replace_one(
            {"project_id": project_id},
            {
                "project_id": project_id,
                "results": results,
                "documentation": documentation,
                "created_at": datetime.utcnow().isoformat()
            },
            upsert=True
        )

        # Actualiza el estado del proyecto con estadísticas finales.
        db.projects.update_one({"_id": project_id}, {
            "$set": {
                "status": "completed",
                "language": results.get("primary_language", "unknown"),
                "updated_at": datetime.utcnow().isoformat(),
                "stats": {
                    "files": results.get("total_files", 0),
                    "functions": len(results.get("functions", [])),
                    "classes": len(results.get("classes", [])),
                    "endpoints": len(results.get("endpoints", [])),
                    "quality_score": results.get("quality_score", 0)
                }
            }
        })
    except Exception as e:
        # Si algo falla, se guarda el error para poder consultarlo desde la UI.
        db.projects.update_one({"_id": project_id}, {
            "$set": {"status": "error", "error_message": str(e)}
        })

@analysis_bp.route('/<project_id>/start', methods=['POST'])
@jwt_required()
def start_analysis(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = project.get('file_path', '')
    thread = threading.Thread(target=run_analysis_async, args=(project_id, project_path, db))
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Analysis started", "project_id": project_id}), 202

@analysis_bp.route('/<project_id>/results', methods=['GET'])
@jwt_required()
def get_results(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    
    result = db.analysis_results.find_one({"project_id": project_id})
    if not result:
        return jsonify({"status": project.get("status", "pending"), "results": None}), 200
    
    return jsonify({"status": "completed", "results": result['results'], "documentation": result['documentation']}), 200

@analysis_bp.route('/<project_id>/status', methods=['GET'])
@jwt_required()
def get_status(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id}, {"status": 1, "error_message": 1})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({"status": project.get("status", "pending"), "error": project.get("error_message")}), 200
