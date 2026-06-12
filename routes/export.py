from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from services.db import get_db
from services.exporter import DocumentExporter
from services.doc_generator import DocGenerator
import os
import traceback
import json

export_bp = Blueprint('export', __name__)

def filter_results_by_selection(results, selected):
    """Filter results based on user selection"""
    if not selected:
        return results
    
    try:
        selected_data = json.loads(selected) if isinstance(selected, str) else selected
    except (json.JSONDecodeError, TypeError):
        return results
    
    filtered = results.copy()
    
    # Filter endpoints
    if 'endpoints' in selected_data and selected_data['endpoints']:
        filtered['endpoints'] = [results['endpoints'][i] for i in selected_data['endpoints'] if i < len(results.get('endpoints', []))]
    
    # Filter functions
    if 'functions' in selected_data and selected_data['functions']:
        filtered['functions'] = [results['functions'][i] for i in selected_data['functions'] if i < len(results.get('functions', []))]
    
    # Filter classes
    if 'classes' in selected_data and selected_data['classes']:
        filtered['classes'] = [results['classes'][i] for i in selected_data['classes'] if i < len(results.get('classes', []))]
    
    # Filter structure
    if 'structure' in selected_data and selected_data['structure']:
        filtered['structure'] = [results['structure'][i] for i in selected_data['structure'] if i < len(results.get('structure', []))]
    
    return filtered

def get_identity_flexible():
    """Acepta JWT del header Authorization O del query param ?token="""
    try:
        verify_jwt_in_request()
        return get_jwt_identity()
    except Exception:
        token = request.args.get('token')
        if token:
            from flask_jwt_extended import decode_token
            try:
                decoded = decode_token(token)
                return decoded.get('sub')
            except Exception:
                pass
    return None

@export_bp.route('/<project_id>/pdf', methods=['GET'])
def export_pdf(project_id):
    user_id = get_identity_flexible()
    if not user_id:
        return jsonify({"error": "No autorizado"}), 401

    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Proyecto no encontrado"}), 404

    result = db.analysis_results.find_one({"project_id": project_id})
    if not result:
        return jsonify({"error": "Sin resultados de análisis"}), 404

    # Get selected items from query parameter
    selected = request.args.get('selected')

    try:
        results_to_use = result.get('results')
        if results_to_use:
            # Filter results based on selection
            if selected:
                results_to_use = filter_results_by_selection(results_to_use, selected)
            documentation = DocGenerator(results_to_use).generate()
            db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
            exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
        else:
            exporter = DocumentExporter(project, result)
        file_path = exporter.to_pdf()

        # Verificar que el archivo existe y tenga contenido
        from pathlib import Path
        path_obj = Path(file_path)
        if not path_obj.exists() or path_obj.stat().st_size < 100:
            raise RuntimeError("Archivo generado no existe o es demasiado pequeño")

        # Si el archivo es HTML (fallback), enviar como HTML con advertencia
        if file_path.endswith('.html'):
            print(f"[Export] PDF falló, enviando HTML como fallback")
            return send_file(
                file_path,
                as_attachment=True,
                download_name=f"{project['name']}_documentacion.html",
                mimetype='text/html'
            )

        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{project['name']}_documentacion.pdf",
            mimetype='application/pdf'
        )
    except Exception as exc:
        error_text = traceback.format_exc()
        print(f"[Export] Error al generar PDF para proyecto {project_id}: {exc}\n{error_text}")
        return jsonify({"error": "Error interno al generar PDF", "details": str(exc)}), 500

@export_bp.route('/<project_id>/html', methods=['GET'])
def export_html(project_id):
    user_id = get_identity_flexible()
    if not user_id:
        return jsonify({"error": "No autorizado"}), 401

    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Proyecto no encontrado"}), 404

    result = db.analysis_results.find_one({"project_id": project_id})
    if not result:
        return jsonify({"error": "Sin resultados de análisis"}), 404

    # Get selected items from query parameter
    selected = request.args.get('selected')

    results_to_use = result.get('results')
    if results_to_use:
        # Filter results based on selection
        if selected:
            results_to_use = filter_results_by_selection(results_to_use, selected)
        documentation = DocGenerator(results_to_use).generate()
        db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
        exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
    else:
        exporter = DocumentExporter(project, result)
    html = exporter.to_html()

    return Response(
        html,
        mimetype='text/html',
        headers={'Content-Disposition': f'attachment; filename={project["name"]}_docs.html'}
    )

@export_bp.route('/<project_id>/markdown', methods=['GET'])
def export_markdown(project_id):
    user_id = get_identity_flexible()
    if not user_id:
        return jsonify({"error": "No autorizado"}), 401

    db = get_db()
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Proyecto no encontrado"}), 404

    result = db.analysis_results.find_one({"project_id": project_id})
    if not result:
        return jsonify({"error": "Sin resultados de análisis"}), 404

    # Get selected items from query parameter
    selected = request.args.get('selected')

    results_to_use = result.get('results')
    if results_to_use:
        # Filter results based on selection
        if selected:
            results_to_use = filter_results_by_selection(results_to_use, selected)
        documentation = DocGenerator(results_to_use).generate()
        db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
        exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
    else:
        exporter = DocumentExporter(project, result)
    md = exporter.to_markdown()

    return Response(
        md,
        mimetype='text/markdown',
        headers={'Content-Disposition': f'attachment; filename={project["name"]}_docs.md'}
    )