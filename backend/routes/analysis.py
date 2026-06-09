from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.analyzer import ProjectAnalyzer
from services.doc_generator import DocGenerator
from services.etl_pipeline import ETLPipeline
from services.ai_enhancer import AIEnhancer
from datetime import datetime
import threading
import requests

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
        # Intentar resolver y normalizar la ruta del proyecto
        from pathlib import Path
        p = None
        if project_path:
            try:
                p = Path(project_path).resolve()
            except Exception:
                p = Path(project_path)

        # Fallback: buscar en carpeta uploads/<project_id> si la ruta no existe
        if not p or not p.exists():
            candidate = Path('uploads') / str(project_id)
            if (candidate / 'src').exists():
                p = (candidate / 'src').resolve()
            elif candidate.exists():
                p = candidate.resolve()

        if not p or not p.exists():
            raise ValueError("No se proporcionó una ruta de proyecto válida. Debes subir un archivo o proporcionar una URL de GitHub.")

        project_path = str(p)

        # Marca el proyecto como en proceso de análisis.
        db.projects.update_one({"_id": project_id}, {"$set": {"status": "analyzing"}})

        # Analiza el proyecto y extrae métricas y estructura.
        analyzer = ProjectAnalyzer(project_path)
        results = analyzer.analyze()

        # Ejecuta minería de datos y mejora documentación con IA si está disponible.
        mining_results = {}
        try:
            ai_enhancer = AIEnhancer()
            print(f"[DEBUG] AI Enhancer disponible: {ai_enhancer.is_available()}")
            try:
                mining_results = ai_enhancer.mine_code_patterns(results)
                print(f"[DEBUG] Mining results: {mining_results}")
                results["mining_results"] = mining_results
            except Exception as e:
                print(f"[DEBUG] AI mining failed: {e}")

            try:
                print("[DEBUG] Mejorando documentación con IA...")
                results = ai_enhancer.enhance_documentation(results)
                print("[DEBUG] Documentación mejorada")
            except Exception as e:
                print(f"[DEBUG] AI enhance failed: {e}")
        except Exception as e:
            print(f"[DEBUG] AI Enhancer initialization failed: {e}")

        # Convierte esos resultados en documentación técnica.
        documentation = ""
        try:
            doc_gen = DocGenerator(results)
            documentation = doc_gen.generate()
        except Exception as e:
            print(f"[DEBUG] DocGenerator failed: {e}")

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
        # Guardar traceback completo para diagnóstico
        import traceback
        tb = traceback.format_exc()
        err_info = {"status": "error", "error_message": str(e), "error_trace": tb}
        try:
            db.projects.update_one({"_id": project_id}, {"$set": err_info})
        except Exception:
            # Si actualizar el proyecto falla, intentar insertar en analysis_results
            pass
        try:
            db.analysis_results.replace_one(
                {"project_id": project_id},
                {"project_id": project_id, "results": {}, "documentation": "", "error": err_info, "created_at": datetime.utcnow().isoformat()},
                upsert=True
            )
        except Exception:
            pass

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

@analysis_bp.route('/suggest-docstring', methods=['POST'])
@jwt_required()
def suggest_docstring():
    """
    Endpoint para generar sugerencias de docstrings usando la API de Groq.
    Usa la clase AIEnhancer para manejar múltiples API keys.
    """
    try:
        from services.ai_enhancer import AIEnhancer
        
        data = request.json
        name = data.get('name', '')
        file = data.get('file', '')
        params = data.get('params', '')
        kind = data.get('kind', 'function')
        lang = data.get('lang', 'Python')
        
        ai = AIEnhancer()
        
        if kind == 'class':
            prompt = f"""Genera SOLO el docstring para esta clase en {lang}. Sin explicaciones, sin código adicional, solo el string de documentación listo para pegar.

Clase: {name}
Archivo: {file}

Formato esperado (Python):
    \"\"\"
    Descripción breve de la clase.

    Attributes:
        attr1: Descripción del atributo.
    \"\"\""""
        else:
            prompt = f"""Genera SOLO el docstring para esta función en {lang}. Sin explicaciones, sin código adicional, solo el string de documentación listo para pegar.

Función: {name}
Parámetros: {params or 'ninguno'}
Archivo: {file}

Formato esperado (Python):
    \"\"\"
    Descripción breve de la función.

    Args:
        param1: Descripción del parámetro.

    Returns:
        Descripción del valor retornado.
    \"\"\""""
        
        # Usar AIEnhancer para generar la sugerencia
        suggestion = ai._call_ai(
            "Eres un experto en generar documentación de código. Genera docstrings claros y concisos.",
            prompt,
            max_tokens=500
        )
        
        if suggestion:
            return jsonify({'suggestion': suggestion}), 200
        else:
            # Si falla la API, devolver un template básico
            if kind == 'class':
                fallback = f'    """\n    {name} — descripción de la clase.\n\n    Attributes:\n        Agrega aquí los atributos principales.\n    """'
            else:
                fallback = f'    """\n    {name} — descripción de la función.\n\n    Args:\n{(params or "").split(",") if params else ""}\n\n    Returns:\n        Describe el valor de retorno.\n    """'
            return jsonify({'suggestion': fallback}), 200

    except Exception as e:
        # En caso de error, devolver un template básico
        data = request.json
        kind = data.get('kind', 'function')
        name = data.get('name', '')
        params = data.get('params', '')
        if kind == 'class':
            fallback = f'    """\n    {name} — descripción de la clase.\n\n    Attributes:\n        Agrega aquí los atributos principales.\n    """'
        else:
            fallback = f'    """\n    {name} — descripción de la función.\n\n    Args:\n{(params or "").split(",") if params else ""}\n\n    Returns:\n        Describe el valor de retorno.\n    """'
        return jsonify({'suggestion': fallback}), 200

@analysis_bp.route('/etl', methods=['POST'])
@jwt_required()
def run_etl_pipeline():
    """
    Endpoint para ejecutar el pipeline ETL completo.

    Configuración esperada en el request body:
    {
        "extract": {
            "source_type": "github|zip|csv|json|directory",
            "source_path": "url o ruta",
            "project_id": "opcional para uploads"
        },
        "transform": {
            "rules": []  # opcional
        },
        "load": {
            "target": "html|pdf|json|mongodb",
            "output_path": "ruta de salida opcional"
        }
    }
    """
    try:
        config = request.json

        if not config:
            return jsonify({"error": "No configuration provided"}), 400

        # Validar configuración
        if "extract" not in config or "load" not in config:
            return jsonify({"error": "Missing extract or load configuration"}), 400

        # Crear y ejecutar pipeline
        pipeline = ETLPipeline()
        result = pipeline.run_pipeline(config)

        if result.get("success"):
            return jsonify({
                "message": "ETL pipeline completed successfully",
                "result": result
            }), 200
        else:
            return jsonify({
                "error": "ETL pipeline failed",
                "result": result
            }), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@analysis_bp.route('/etl/diagram', methods=['GET'])
@jwt_required()
def get_etl_diagram():
    """
    Retorna el diagrama PlantUML del pipeline ETL.
    """
    try:
        pipeline = ETLPipeline()
        diagram = pipeline.get_pipeline_diagram()
        return jsonify({"diagram": diagram}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
