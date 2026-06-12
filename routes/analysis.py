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
import re

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

    # Verificar límite de análisis según el plan del usuario
    try:
        # Cargar definición de planes (import local para evitar ciclos)
        from routes.payments import PLANS
        user = db.users.find_one({"_id": user_id}) or {}
        plan_key = user.get('plan', 'free')
        analyses_limit = PLANS.get(plan_key, {}).get('analyses_per_month', -1)

        if analyses_limit != -1:
            # Calcular inicio del mes en formato ISO (coincide con el formato guardado)
            now = datetime.utcnow()
            start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

            # Obtener ids de proyectos del usuario
            project_ids = [p['_id'] for p in db.projects.find({"user_id": user_id}, {"_id": 1})]

            # Contar análisis realizados en el mes actual para los proyectos del usuario
            current_analyses = 0
            if project_ids:
                current_analyses = db.analysis_results.count_documents({
                    "project_id": {"$in": project_ids},
                    "created_at": {"$gte": start_month}
                })

            if current_analyses >= analyses_limit:
                return jsonify({"error": f"Has alcanzado el límite de análisis para tu plan ({plan_key}). Límite mensual: {analyses_limit}."}), 400
    except Exception:
        # En caso de error al verificar límites, continuar y permitir el análisis (no bloquear por fallo del check)
        pass

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

@analysis_bp.route('/database/analyze-sql', methods=['POST'])
@jwt_required()
def analyze_sql_database():
    sql_file = request.files.get('file')
    if not sql_file or not sql_file.filename.lower().endswith('.sql'):
        return jsonify({"error": "Debes subir un archivo .sql válido."}), 400

    try:
        raw_sql = sql_file.read().decode('utf-8', errors='replace')
    except Exception as e:
        return jsonify({"error": f"Error leyendo el archivo: {str(e)}"}), 400

    analysis = generate_sql_analysis(raw_sql)
    return jsonify(analysis), 200


@analysis_bp.route('/database/download-pdf', methods=['POST'])
@jwt_required()
def download_database_pdf():
    data = request.json
    if not data or not data.get('analysis'):
        return jsonify({"error": "No analysis data provided"}), 400
    
    try:
        from services.doc_generator import DocGenerator
        from io import BytesIO
        from weasyprint import HTML, CSS
        from datetime import datetime
        
        analysis = data.get('analysis', {})
        tables = analysis.get('tables', [])
        suggestions = analysis.get('suggestions', [])
        er_diagram = analysis.get('er_diagram', '')
        
        # Generar HTML del PDF
        html_content = generate_database_pdf_html(tables, suggestions, er_diagram)
        
        # Convertir HTML a PDF con WeasyPrint
        pdf_bytes = HTML(string=html_content).write_pdf()
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'database_analysis_{timestamp}.pdf'
        
        return pdf_bytes, 200, {
            'Content-Type': 'application/pdf',
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    except Exception as e:
        print(f"[PDF Error] {str(e)}")
        return jsonify({"error": f"Error generando PDF: {str(e)}"}), 500


def generate_database_pdf_html(tables, suggestions, er_diagram):
    """Genera HTML profesional para el PDF del análisis de BD."""
    from datetime import datetime
    
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    
    suggestions_html = '\n'.join(f'<li>{s}</li>' for s in suggestions)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Análisis de Base de Datos</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                color: #333;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
            }}
            .header {{
                border-bottom: 3px solid #38bdf8;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .header h1 {{
                margin: 0;
                color: #0f172a;
                font-size: 32px;
            }}
            .timestamp {{
                color: #666;
                font-size: 12px;
                margin-top: 10px;
            }}
            .section {{
                margin-bottom: 30px;
                page-break-inside: avoid;
            }}
            .section h2 {{
                border-left: 4px solid #38bdf8;
                padding-left: 10px;
                color: #0f172a;
                margin-top: 20px;
            }}
            .section h3 {{
                color: #334155;
                margin-top: 15px;
            }}
            ul {{
                padding-left: 20px;
            }}
            li {{
                margin-bottom: 8px;
                color: #555;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 10px;
                text-align: left;
            }}
            th {{
                background-color: #38bdf8;
                color: white;
                font-weight: bold;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            .diagram {{
                text-align: center;
                margin: 20px 0;
                page-break-inside: avoid;
            }}
            .diagram img {{
                max-width: 100%;
                height: auto;
                border: 1px solid #ddd;
                padding: 10px;
                background-color: #fff;
            }}
            .footer {{
                margin-top: 40px;
                border-top: 1px solid #ddd;
                padding-top: 10px;
                color: #999;
                font-size: 12px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Análisis de Base de Datos</h1>
            <p class="timestamp">Generado: {timestamp}</p>
        </div>

        <div class="section">
            <h2>Resumen</h2>
            <p>Se detectaron <strong>{len(tables)}</strong> tabla(s) en el archivo SQL analizado.</p>
            <p>Este informe contiene un análisis detallado de la estructura, recomendaciones de optimización y un diagrama entidad-relación.</p>
        </div>

        <div class="section">
            <h2>Diagrama Entidad-Relación (E-R)</h2>
            <div class="diagram">
                {er_diagram if er_diagram else '<p style="color: #999;">No se pudo generar el diagrama E-R.</p>'}
            </div>
        </div>

        <div class="section">
            <h2>Tablas Detectadas</h2>
            <p>Total de tablas: <strong>{len(tables)}</strong></p>
            <ul>
                {''.join(f'<li><code>{table}</code></li>' for table in tables)}
            </ul>
        </div>

        <div class="section">
            <h2>Recomendaciones y Observaciones</h2>
            <ul>
                {suggestions_html}
            </ul>
        </div>

        <div class="footer">
            <p>AutoDocs AI - Análisis automático de bases de datos</p>
        </div>
    </body>
    </html>
    """
    return html


def generate_sql_analysis(sql_text):
    suggestions = []
    tables = []
    table_columns = {}
    foreign_keys = {}
    
    content = sql_text
    # Buscar todas las tablas CREATE TABLE
    matches = re.findall(r'create\s+table\s+[`"\[]?(\w+)[`"\]]?\s*\((.*?)\)\s*(?:;|$)', content, flags=re.S | re.I)

    if not matches:
        suggestions.append('No se detectaron sentencias CREATE TABLE. Verifica que el archivo sea un esquema SQL válido.')
    else:
        tables = [name for name, _ in matches]
        suggestions.append(f'Se detectaron {len(tables)} tabla(s) en el archivo.')

        lower_content = content.lower()
        has_index = bool(re.search(r'create\s+(?:unique\s+)?index\s+', lower_content))

        for table_name, body in matches:
            # Extraer columnas
            columns = []
            for line in body.split(','):
                line = line.strip()
                if line and not line.upper().startswith(('PRIMARY', 'FOREIGN', 'UNIQUE', 'INDEX', 'KEY', 'CONSTRAINT')):
                    parts = line.split()
                    if len(parts) >= 2:
                        col_name = parts[0].strip('`"[]')
                        col_type = parts[1]
                        columns.append({'name': col_name, 'type': col_type})
            
            table_columns[table_name] = columns
            
            lower_body = body.lower()
            if 'primary key' not in lower_body:
                suggestions.append(f'La tabla `{table_name}` no define una clave primaria. Agrega `PRIMARY KEY` para mejorar integridad y rendimiento.')

            fk_columns = sorted(set(re.findall(r'(\w+_id)\b', body, flags=re.I)))
            if fk_columns and 'foreign key' not in lower_body:
                suggestions.append(f'Tabla `{table_name}` tiene columnas que parecen llaves foráneas ({", ".join(fk_columns)}) sin FOREIGN KEY declarado.')

            if re.search(r'varchar\s*(?!\()', body, flags=re.I):
                suggestions.append(f'Tabla `{table_name}` contiene columnas VARCHAR sin tamaño definido. Usa `VARCHAR(255)` o un tamaño específico.')

            for col_name, col_type in re.findall(r'(\w+)\s+(text|blob|longtext|mediumtext|tinytext)\b', body, flags=re.I):
                suggestions.append(f'La columna `{col_name}` en `{table_name}` usa `{col_type}`. Si no necesitas texto libre ilimitado, considera tipos más ajustados.')

            if not has_index and 'foreign key' not in lower_body:
                suggestions.append(f'No se detectan índices explícitos para `{table_name}`. Agrega índices a columnas de búsqueda frecuentes o a las relaciones.')
            
            # Extraer relaciones foráneas
            fk_matches = re.findall(r'foreign\s+key\s*\(\s*(\w+)\s*\)\s*references\s+(\w+)', body, flags=re.I)
            for fk_col, ref_table in fk_matches:
                foreign_keys[table_name] = {'column': fk_col, 'references': ref_table}

    # Generar diagrama E-R en PlantUML
    er_diagram_code = generate_er_diagram_plantuml(tables, table_columns, foreign_keys)
    er_diagram_html = generate_er_diagram_image(er_diagram_code)

    summary = 'Análisis completado exitosamente.'
    return {
        'summary': summary,
        'tables': tables,
        'suggestions': suggestions,
        'er_diagram': er_diagram_html,
        'er_diagram_code': er_diagram_code
    }


def generate_er_diagram_plantuml(tables, table_columns, foreign_keys):
    """Genera código PlantUML para diagrama E-R."""
    plantuml_code = "@startuml database\n"
    plantuml_code += "!theme plain\n"
    plantuml_code += "skinparam backgroundColor #f1f5f9\n"
    plantuml_code += "skinparam rectangle {\n"
    plantuml_code += "  BackgroundColor #38bdf8\n"
    plantuml_code += "  BorderColor #0f172a\n"
    plantuml_code += "  FontColor #0f1418\n"
    plantuml_code += "}\n\n"

    # Definir entidades
    for table in tables:
        columns = table_columns.get(table, [])
        plantuml_code += f"entity \"{table}\" {{\n"
        for col in columns[:8]:  # Límitar a 8 columnas por tabla
            plantuml_code += f"  {col['name']}: {col['type']}\n"
        if len(columns) > 8:
            plantuml_code += f"  ... ({len(columns) - 8} more columns)\n"
        plantuml_code += "}\n\n"

    # Definir relaciones
    for table, fk_info in foreign_keys.items():
        ref_table = fk_info.get('references')
        if ref_table in tables:
            plantuml_code += f"{table} }}--|| {ref_table}\n"

    plantuml_code += "@enduml\n"
    return plantuml_code


def generate_er_diagram_image(plantuml_code):
    """Genera imagen del diagrama E-R usando PlantUML."""
    try:
        from services.doc_generator import DocGenerator
        doc_gen = DocGenerator({})
        
        # Intentar usar el servidor remoto de PlantUML
        from pathlib import Path
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.puml', delete=False) as f:
            f.write(plantuml_code)
            temp_path = Path(f.name)
        
        try:
            # Usar el método _fetch_plantuml_image del DocGenerator
            output_file = temp_path.with_suffix('.png')
            result_path = doc_gen._fetch_plantuml_image(plantuml_code, output_file)
            
            if result_path and result_path.exists():
                data_uri = doc_gen._image_to_data_uri(result_path)
                if data_uri:
                    return f'<img src="{data_uri}" alt="Diagrama E-R" />'
                result_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[ER Diagram] Error: {e}")
        finally:
            temp_path.unlink(missing_ok=True)
        
        # Fallback: mostrar el código PlantUML
        return f'<pre style="background:#f0f0f0; padding:10px; border-radius:4px; font-size:12px; overflow:auto;">{plantuml_code}</pre>'
    except Exception as e:
        print(f"[ER Diagram] Fallback error: {e}")
        return '<p style="color: #999;">No se pudo generar el diagrama E-R.</p>'
