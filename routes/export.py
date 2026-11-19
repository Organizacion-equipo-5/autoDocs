from flask import Blueprint, request, jsonify, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from services.db import get_db
from services.exporter import DocumentExporter
from services.doc_generator import DocGenerator
from datetime import datetime
import os
import re
import traceback
import json

export_bp = Blueprint('export', __name__)


def _build_export_filename(project_name: str, ext: str) -> str:
    """Construye un nombre de archivo seguro con el nombre del proyecto y fecha/hora actual."""
    clean_name = re.sub(r'[^\w\-.]', '_', str(project_name).strip())
    clean_name = re.sub(r'_+', '_', clean_name).strip('_') or 'proyecto'
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    return f"{clean_name}_{timestamp}.{ext}"


def _log_export_event(db, user_id, project_id, export_type, metadata=None):
    """Guarda un registro simple de exportación para alimentar recomendaciones futuras."""
    try:
        entry = {
            "user_id": user_id,
            "action": export_type,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": {"project_id": project_id, **(metadata or {})},
        }
        db.usage_logs.insert_one(entry)
    except Exception as exc:
        print(f"[Export] No se pudo registrar el uso de exportación: {exc}")


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


def _normalize_lang(value):
    """Normaliza cualquier variante de idioma a 'es'/'en'."""
    if not value:
        return None
    value = str(value).strip().lower()
    if value.startswith('en'):
        return 'en'
    if value.startswith('es'):
        return 'es'
    return None


def _get_request_lang(default='es'):
    """Idioma explícito de la petición (query/header) o el valor por defecto."""
    lang = None
    for key in ('lang', 'language', 'doc_language', 'output_language'):
        lang = _normalize_lang(request.args.get(key))
        if lang:
            return lang

    # Accept-Language puede traer varias preferencias: "es-ES,es;q=0.9,en;q=0.8"
    for part in request.headers.get('Accept-Language', '').split(','):
        code = part.split(';', 1)[0].strip()
        lang = _normalize_lang(code)
        if lang:
            return lang

    return _normalize_lang(default) or 'es'


def _resolve_saved_lang(db, user_id, project_id, result=None):
    """Idioma guardado para el proyecto/cuenta, sin usar el lenguaje de código."""
    project = db.projects.find_one(
        {"_id": project_id},
        {"doc_language": 1, "preferred_language": 1, "language_code": 1},
    ) or {}
    candidates = [
        (result or {}).get('results', {}).get('doc_language'),
        project.get('doc_language'),
        project.get('preferred_language'),
        project.get('language_code'),
    ]
    user = db.users.find_one(
        {"_id": user_id},
        {"language": 1, "preferred_language": 1},
    ) or {}
    candidates.extend([user.get('language'), user.get('preferred_language')])

    for candidate in candidates:
        lang = _normalize_lang(candidate)
        if lang:
            return lang
    return 'es'

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
    lang = _get_request_lang(_resolve_saved_lang(db, user_id, project_id, result))

    try:
        results_to_use = result.get('results')
        if results_to_use:
            # Filter results based on selection
            if selected:
                results_to_use = filter_results_by_selection(results_to_use, selected)
            if isinstance(results_to_use, dict):
                results_to_use['doc_language'] = lang
            try:
                documentation = DocGenerator(results_to_use, lang=lang).generate()
            except TypeError:
                documentation = DocGenerator(results_to_use).generate()
            db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
            try:
                exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation}, lang=lang)
            except TypeError:
                exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
        else:
            try:
                exporter = DocumentExporter(project, result, lang=lang)
            except TypeError:
                exporter = DocumentExporter(project, result)
        file_path = exporter.to_pdf()

        # Verificar que el archivo existe y tenga contenido
        from pathlib import Path
        path_obj = Path(file_path)
        if not path_obj.exists() or path_obj.stat().st_size < 100:
            raise RuntimeError("Archivo generado no existe o es demasiado pequeño")

        # Si el archivo es HTML (fallback), enviar como HTML con advertencia
        _log_export_event(
            db,
            user_id,
            project_id,
            "export_pdf",
            {"format": "pdf", "selected": bool(selected), "fallback_html": file_path.endswith('.html')},
        )

        if file_path.endswith('.html'):
            print(f"[Export] PDF falló, enviando HTML como fallback")
            html_name = _build_export_filename(project.get('name', 'proyecto'), 'html')
            resp = send_file(
                file_path,
                as_attachment=True,
                download_name=html_name,
                mimetype='text/html'
            )
            resp.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return resp

        pdf_name = _build_export_filename(project.get('name', 'proyecto'), 'pdf')
        resp = send_file(
            file_path,
            as_attachment=True,
            download_name=pdf_name,
            mimetype='application/pdf'
        )
        resp.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return resp
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
    lang = _get_request_lang(_resolve_saved_lang(db, user_id, project_id, result))

    results_to_use = result.get('results')
    if results_to_use:
        # Filter results based on selection
        if selected:
            results_to_use = filter_results_by_selection(results_to_use, selected)
        if isinstance(results_to_use, dict):
            results_to_use['doc_language'] = lang
        try:
            documentation = DocGenerator(results_to_use, lang=lang).generate()
        except TypeError:
            documentation = DocGenerator(results_to_use).generate()
        db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
        try:
            exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation}, lang=lang)
        except TypeError:
            exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
    else:
        try:
            exporter = DocumentExporter(project, result, lang=lang)
        except TypeError:
            exporter = DocumentExporter(project, result)
    html = exporter.to_html()
    _log_export_event(db, user_id, project_id, "export_html", {"format": "html", "selected": bool(selected)})

    filename = _build_export_filename(project.get('name', 'proyecto'), 'html')
    return Response(
        html,
        mimetype='text/html',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
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
    lang = _get_request_lang(_resolve_saved_lang(db, user_id, project_id, result))

    results_to_use = result.get('results')
    if results_to_use:
        # Filter results based on selection
        if selected:
            results_to_use = filter_results_by_selection(results_to_use, selected)
        if isinstance(results_to_use, dict):
            results_to_use['doc_language'] = lang
        try:
            documentation = DocGenerator(results_to_use, lang=lang).generate()
        except TypeError:
            documentation = DocGenerator(results_to_use).generate()
        db.analysis_results.update_one({"project_id": project_id}, {"$set": {"documentation": documentation}})
        try:
            exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation}, lang=lang)
        except TypeError:
            exporter = DocumentExporter(project, {"results": results_to_use, "documentation": documentation})
    else:
        try:
            exporter = DocumentExporter(project, result, lang=lang)
        except TypeError:
            exporter = DocumentExporter(project, result)
    md = exporter.to_markdown()
    _log_export_event(db, user_id, project_id, "export_markdown", {"format": "markdown", "selected": bool(selected)})

    filename = _build_export_filename(project.get('name', 'proyecto'), 'md')
    return Response(
        md,
        mimetype='text/markdown',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
    )