from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.analyzer import ProjectAnalyzer
from services.doc_generator import DocGenerator
from services.etl_pipeline import ETLPipeline
from services.ai_enhancer import AIEnhancer
from services.ml_analyzer import run_ml_analysis
from datetime import datetime
from utils.usage_tracker import log_usage_manual
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
        from pathlib import Path
        p = None
        if project_path:
            try:
                p = Path(project_path).resolve()
            except Exception:
                p = Path(project_path)

        if not p or not p.exists():
            candidate = Path('uploads') / str(project_id)
            if (candidate / 'src').exists():
                p = (candidate / 'src').resolve()
            elif candidate.exists():
                p = candidate.resolve()

        if not p or not p.exists():
            raise ValueError("No se proporcionó una ruta de proyecto válida. Debes subir un archivo o proporcionar una URL de GitHub.")

        project_path = str(p)

        db.projects.update_one({"_id": project_id}, {"$set": {"status": "analyzing"}})

        analyzer = ProjectAnalyzer(project_path)
        results = analyzer.analyze()

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

        documentation = ""
        try:
            doc_gen = DocGenerator(results)
            documentation = doc_gen.generate()
        except Exception as e:
            print(f"[DEBUG] DocGenerator failed: {e}")

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
        import traceback
        tb = traceback.format_exc()
        err_info = {"status": "error", "error_message": str(e), "error_trace": tb}
        try:
            db.projects.update_one({"_id": project_id}, {"$set": err_info})
        except Exception:
            pass
        try:
            db.analysis_results.replace_one(
                {"project_id": project_id},
                {
                    "project_id": project_id,
                    "results": {},
                    "documentation": "",
                    "error": err_info,
                    "created_at": datetime.utcnow().isoformat()
                },
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

    try:
        from routes.payments import PLANS
        user = db.users.find_one({"_id": user_id}) or {}
        plan_key = user.get('plan', 'free')
        analyses_limit = PLANS.get(plan_key, {}).get('analyses_per_month', -1)

        if analyses_limit != -1:
            now = datetime.utcnow()
            start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            project_ids = [p['_id'] for p in db.projects.find({"user_id": user_id}, {"_id": 1})]
            current_analyses = 0
            if project_ids:
                current_analyses = db.analysis_results.count_documents({
                    "project_id": {"$in": project_ids},
                    "created_at": {"$gte": start_month}
                })
            if current_analyses >= analyses_limit:
                return jsonify({
                    "error": f"Has alcanzado el límite de análisis para tu plan ({plan_key}). Límite mensual: {analyses_limit}."
                }), 400
    except Exception:
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

    return jsonify({
        "status": "completed",
        "results": result['results'],
        "documentation": result['documentation']
    }), 200


@analysis_bp.route('/<project_id>/status', methods=['GET'])
@jwt_required()
def get_status(project_id):
    user_id = get_jwt_identity()
    db = get_db()
    project = db.projects.find_one(
        {"_id": project_id, "user_id": user_id},
        {"status": 1, "error_message": 1}
    )
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify({
        "status": project.get("status", "pending"),
        "error": project.get("error_message")
    }), 200


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

        suggestion = ai._call_ai(
            "Eres un experto en generar documentación de código. Genera docstrings claros y concisos.",
            prompt,
            max_tokens=500
        )

        if suggestion:
            return jsonify({'suggestion': suggestion}), 200
        else:
            if kind == 'class':
                fallback = f'    """\n    {name} — descripción de la clase.\n\n    Attributes:\n        Agrega aquí los atributos principales.\n    """'
            else:
                fallback = f'    """\n    {name} — descripción de la función.\n\n    Args:\n        Agrega aquí los parámetros.\n\n    Returns:\n        Describe el valor de retorno.\n    """'
            return jsonify({'suggestion': fallback}), 200

    except Exception as e:
        data = request.json or {}
        kind = data.get('kind', 'function')
        name = data.get('name', '')
        if kind == 'class':
            fallback = f'    """\n    {name} — descripción de la clase.\n\n    Attributes:\n        Agrega aquí los atributos principales.\n    """'
        else:
            fallback = f'    """\n    {name} — descripción de la función.\n\n    Args:\n        Agrega aquí los parámetros.\n\n    Returns:\n        Describe el valor de retorno.\n    """'
        return jsonify({'suggestion': fallback}), 200

@analysis_bp.route('/<project_id>/predictions', methods=['GET'])
@jwt_required()
def get_predictions(project_id):
    """
    Ejecuta los modelos de ML sobre los resultados ya analizados
    del proyecto y devuelve regresiones + matriz de confusión.
    """
    user_id = get_jwt_identity()
    db = get_db()
 
    project = db.projects.find_one({"_id": project_id, "user_id": user_id})
    if not project:
        return jsonify({"error": "Proyecto no encontrado"}), 404
 
    result = db.analysis_results.find_one({"project_id": project_id})
    if not result:
        return jsonify({"error": "El proyecto aún no tiene resultados de análisis"}), 404
 
    try:
        from services.ml_analyzer import run_ml_analysis

        # 🆕 Reunir los proyectos analizados del usuario para entrenar el
        # árbol de decisión con datos reales cuando haya suficientes.
        all_projects_data = []
        try:
            user_projects = list(db.projects.find({"user_id": user_id}))
            user_project_ids = [p["_id"] for p in user_projects]
            user_analyses = list(db.analysis_results.find({"project_id": {"$in": user_project_ids}}))
            analysis_by_project = {a.get("project_id"): a for a in user_analyses if a.get("project_id")}
            for proj in user_projects:
                analysis = analysis_by_project.get(proj.get("_id"))
                if analysis and analysis.get("results"):
                    all_projects_data.append({"results": analysis["results"], "project": proj})
        except Exception as e:
            print(f"[WARN] No se pudo construir dataset de proyectos reales: {e}")

        ml_results = run_ml_analysis(result["results"], all_projects_data=all_projects_data)
        print(f"[DEBUG] ML results for project {project_id}:")
        print(f"  - regresion_simple: {ml_results.get('regresion_simple', {}).keys() if ml_results.get('regresion_simple') else 'None'}")
        print(f"  - regresion_multiple: {ml_results.get('regresion_multiple', {}).keys() if ml_results.get('regresion_multiple') else 'None'}")
        print(f"  - regresion_logistica: {ml_results.get('regresion_logistica', {}).keys() if ml_results.get('regresion_logistica') else 'None'}")
        return jsonify({"status": "ok", "predictions": ml_results}), 200
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[ERROR] ML prediction failed for project {project_id}: {str(e)}")
        print(tb)
        return jsonify({"error": f"Error en análisis ML: {str(e)}", "trace": tb}), 500

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
            "rules": []
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
        if "extract" not in config or "load" not in config:
            return jsonify({"error": "Missing extract or load configuration"}), 400

        pipeline = ETLPipeline()
        result = pipeline.run_pipeline(config)

        if result.get("success"):
            return jsonify({"message": "ETL pipeline completed successfully", "result": result}), 200
        else:
            return jsonify({"error": "ETL pipeline failed", "result": result}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analysis_bp.route('/etl/diagram', methods=['GET'])
@jwt_required()
def get_etl_diagram():
    """Retorna el diagrama PlantUML del pipeline ETL."""
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
        html_content = generate_database_pdf_html(analysis)
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


def generate_database_pdf_html(analysis):
    """Genera HTML profesional para el PDF del análisis de BD."""
    from datetime import datetime

    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    tables = analysis.get('tables', [])
    stats = analysis.get('stats', {})
    table_columns = analysis.get('table_columns', {})
    suggestions = analysis.get('suggestions', [])
    er_diagram = analysis.get('er_diagram', '')
    data_sources = analysis.get('data_sources', {})
    structured = data_sources.get('structured', [])
    semi_structured = data_sources.get('semi_structured', [])
    unstructured = data_sources.get('unstructured', [])
    warehouse_schema = analysis.get('warehouse_schema', {})
    ai_summary = analysis.get('ai_summary', '')
    snowflake_diagram = analysis.get('snowflake_diagram', '')
    preparation_items = analysis.get('data_preparation', [])
    mining_items = analysis.get('data_mining_insights', [])

    suggestions_html = '\n'.join(f'<li>{s}</li>' for s in suggestions)
    preparation_html = (
        '<ul>' + ''.join(f'<li>{item}</li>' for item in preparation_items) + '</ul>'
        if preparation_items
        else '<p>No se encontraron recomendaciones de preparación de datos.</p>'
    )
    mining_html = (
        '<ul>' + ''.join(f'<li>{item}</li>' for item in mining_items) + '</ul>'
        if mining_items
        else '<p>No se detectaron insights de minería de datos.</p>'
    )

    tables_structure_html = ''
    for table_name in tables:
        columns = table_columns.get(table_name, [])
        if not columns:
            tables_structure_html += f'<p><code>{table_name}</code></p>'
            continue
        rows = ''.join(
            f'<tr><td>{col["name"]}</td><td>{col["type"]}</td></tr>'
            for col in columns
        )
        tables_structure_html += f'''
        <h3>{table_name}</h3>
        <table>
            <thead><tr><th>Columna</th><th>Tipo</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>'''

    total_tables = stats.get('total_tables', len(tables))
    fk_relations = stats.get('fk_relations', len(analysis.get('foreign_keys', {})))
    tables_with_pk = stats.get('tables_with_pk', 0)
    summary_text = analysis.get('summary', 'Análisis completado exitosamente.')

    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Análisis de Base de Datos</title>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 20px; }}
            .header {{ border-bottom: 3px solid #38bdf8; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h1 {{ margin: 0; color: #0f172a; font-size: 32px; }}
            .timestamp {{ color: #666; font-size: 12px; margin-top: 10px; }}
            .section {{ margin-bottom: 30px; page-break-inside: avoid; }}
            .section h2 {{ border-left: 4px solid #38bdf8; padding-left: 10px; color: #0f172a; margin-top: 20px; }}
            .section h3 {{ color: #334155; margin-top: 15px; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; color: #555; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #38bdf8; color: white; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .diagram {{ text-align: center; margin: 20px 0; page-break-inside: avoid; }}
            .diagram img {{ max-width: 100%; height: auto; border: 1px solid #ddd; padding: 10px; background-color: #fff; }}
            .footer {{ margin-top: 40px; border-top: 1px solid #ddd; padding-top: 10px; color: #999; font-size: 12px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Análisis de Base de Datos</h1>
            <p class="timestamp">Generado: {timestamp}</p>
        </div>

        <div class="section">
            <h2>Resumen</h2>
            <p>{summary_text}</p>
            <p><strong>Tablas:</strong> {total_tables} · <strong>Relaciones FK:</strong> {fk_relations} · <strong>Con PK:</strong> {tables_with_pk}/{total_tables or 1}</p>
        </div>

        <div class="section">
            <h2>Diagrama Entidad-Relación (E-R)</h2>
            <div class="diagram">
                {er_diagram if er_diagram else '<p style="color:#999;">No se pudo generar el diagrama E-R.</p>'}
            </div>
        </div>

        <div class="section">
            <h2>Tablas Detectadas</h2>
            <p>Total de tablas: <strong>{total_tables}</strong></p>
            {tables_structure_html if tables_structure_html else '<p>No se encontraron tablas.</p>'}
        </div>

        <div class="section">
            <h2>Fuentes y Tipos de Datos</h2>
            <p><strong>Datos Estructurados:</strong> {len(structured)} objetos</p>
            {''.join(f'<li>{item}</li>' for item in structured) if structured else '<p>No se detectaron tablas estructuradas.</p>'}
            <p><strong>Datos Semi-estructurados:</strong> {len(semi_structured)} campos</p>
            {''.join(f'<li>{item}</li>' for item in semi_structured) if semi_structured else '<p>No se detectaron campos semi-estructurados.</p>'}
            <p><strong>Datos No Estructurados:</strong> {len(unstructured)} elementos</p>
            {''.join(f'<li>{item}</li>' for item in unstructured) if unstructured else '<p>No se detectaron datos no estructurados.</p>'}
        </div>

        <div class="section">
            <h2>Preparación de datos</h2>
            {preparation_html}
        </div>

        <div class="section">
            <h2>Minería de datos</h2>
            {mining_html}
        </div>

        <div class="section">
            <h2>Esquema de Data Warehouse</h2>
            <p><strong>Tipo:</strong> {warehouse_schema.get('type', 'N/A')}</p>
            <p>{warehouse_schema.get('description', '')}</p>
            {snowflake_diagram if snowflake_diagram else '<p>No se pudo generar un diagrama de esquema tipo copo de nieve.</p>'}
        </div>

        <div class="section">
            <h2>Resumen IA</h2>
            <p>{ai_summary or 'No se generó resumen de IA. Configura GROQ_API_KEY en .env si quieres habilitarlo.'}</p>
        </div>

        <div class="section">
            <h2>Recomendaciones y Observaciones</h2>
            <ul>{suggestions_html}</ul>
        </div>

        <div class="footer">
            <p>AutoDocs AI - Análisis automático de bases de datos</p>
        </div>
    </body>
    </html>
    """
    return html


def extract_create_tables(sql_text):
    """Extrae sentencias CREATE TABLE respetando paréntesis anidados."""
    cleaned = re.sub(r'/\*[\s\S]*?\*/', '', sql_text)
    cleaned = re.sub(r'--[^\n]*', '', cleaned)
    pattern = re.compile(
        r'create\s+table\s+(?:if\s+not\s+exists\s+)?'
        r'(?:[`"\[]?(?:\w+\.)?[`"\]]?\.)?[`"\[]?(\w+)[`"\]]?\s*\(',
        re.I
    )
    tables = []
    pos = 0
    while True:
        match = pattern.search(cleaned, pos)
        if not match:
            break
        table_name = match.group(1)
        start_body = match.end() - 1
        depth = 0
        end_body = None
        for i in range(start_body, len(cleaned)):
            char = cleaned[i]
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    end_body = i
                    break
        if end_body is None:
            break
        body = cleaned[start_body + 1:end_body]
        tables.append((table_name, body))
        pos = end_body + 1
    return tables


def _split_sql_column_definitions(body):
    """Divide definiciones de columnas respetando paréntesis anidados."""
    parts = []
    current = []
    depth = 0
    for char in body:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            part = ''.join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(char)
    part = ''.join(current).strip()
    if part:
        parts.append(part)
    return parts

def generate_sql_analysis(sql_text):
    suggestions = []
    tables = []
    table_columns = {}
    foreign_keys = {}
    table_pk_status = {}
    table_primary_keys = {}

    content = sql_text
    matches = extract_create_tables(content)
    has_index = bool(re.search(r'create\s+(?:unique\s+)?index\s+', content, flags=re.I))

    if not matches:
        suggestions.append('No se detectaron sentencias CREATE TABLE. Verifica que el archivo sea un esquema SQL válido.')
    else:
        tables = [name for name, _ in matches]
        suggestions.append(f'Se detectaron {len(tables)} tabla(s) en el archivo.')

        for table_name, body in matches:
            columns = []
            primary_keys = []
            table_foreign_keys = []

            for line in _split_sql_column_definitions(body):
                line = line.strip()
                if not line:
                    continue

                pk_inline = re.search(
                    r'^[`"\[]?(\w+)[`"\]]?\s+.+\bprimary\s+key\b',
                    line,
                    flags=re.I
                )
                if pk_inline:
                    primary_keys.append(pk_inline.group(1))

                pk_match = re.search(r'primary\s+key\s*\(([^)]+)\)', line, flags=re.I)
                if pk_match:
                    for key in pk_match.group(1).split(','):
                        key_name = key.strip().strip('`"[]')
                        if key_name:
                            primary_keys.append(key_name)
                    continue

                fk_match = re.search(
                    r'foreign\s+key\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)\s*references\s+[`"\[]?(\w+)[`"\]]?\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)',
                    line,
                    flags=re.I
                )
                if fk_match:
                    fk_info = {
                        'column': fk_match.group(1),
                        'references': fk_match.group(2),
                        'ref_column': fk_match.group(3),
                    }
                    table_foreign_keys.append(fk_info)
                    foreign_keys[table_name] = fk_info
                    continue

                upper_line = line.upper()
                if upper_line.startswith(('PRIMARY', 'FOREIGN', 'UNIQUE', 'INDEX', 'KEY', 'CONSTRAINT')):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    col_name = parts[0].strip('`"[]')
                    col_type = parts[1]
                    nullable = 'NOT NULL' not in upper_line
                    columns.append({
                        'name': col_name,
                        'type': col_type,
                        'nullable': nullable,
                    })

            table_columns[table_name] = columns
            primary_keys = list(dict.fromkeys(primary_keys))
            table_primary_keys[table_name] = primary_keys
            table_pk_status[table_name] = bool(primary_keys) or 'primary key' in body.lower()

            if not table_pk_status[table_name]:
                suggestions.append(
                    f'La tabla `{table_name}` no define una clave primaria. '
                    f'Agrega `PRIMARY KEY` para mejorar integridad y rendimiento.'
                )

            fk_columns = sorted(set(re.findall(r'(\w+_id)\b', body, flags=re.I)))
            lower_body = body.lower()
            if fk_columns and 'foreign key' not in lower_body:
                suggestions.append(
                    f'Tabla `{table_name}` tiene columnas que parecen llaves foráneas '
                    f'({", ".join(fk_columns)}) sin FOREIGN KEY declarado.'
                )

            if re.search(r'varchar\s*(?!\()', body, flags=re.I):
                suggestions.append(
                    f'Tabla `{table_name}` contiene columnas VARCHAR sin tamaño definido. '
                    f'Usa `VARCHAR(255)` o un tamaño específico.'
                )

            for col_name, col_type in re.findall(
                r'(\w+)\s+(text|blob|longtext|mediumtext|tinytext)\b', body, flags=re.I
            ):
                suggestions.append(
                    f'La columna `{col_name}` en `{table_name}` usa `{col_type}`. '
                    f'Si no necesitas texto libre ilimitado, considera tipos más ajustados.'
                )

            if not has_index and 'foreign key' not in lower_body:
                suggestions.append(
                    f'No se detectan índices explícitos para `{table_name}`. '
                    f'Agrega índices a columnas de búsqueda frecuentes o a las relaciones.'
                )

    # Clasificar tipos de datos
    structured = [f'Tabla `{table}`' for table in tables]
    semi_structured = []
    unstructured = []
    text_columns = []
    json_columns = []

    for table_name, cols in table_columns.items():
        for c in cols:
            col_type = c['type'].lower()
            label = f'Campo `{c["name"]}` en `{table_name}` ({c["type"]})'
            if any(k in col_type for k in ['json', 'jsonb', 'xml', 'hstore', 'array']):
                semi_structured.append(label)
                json_columns.append(label)
            elif any(k in col_type for k in ['text', 'blob', 'longtext', 'mediumtext', 'tinytext']):
                if label not in semi_structured:
                    semi_structured.append(label)
                text_columns.append(label)
            else:
                structured.append(label)

    # Detectar esquema de Data Warehouse
    schema_type = 'estructura simple'
    warehouse_description = 'No se detectó un esquema de Data Warehouse evidente.'
    if len(tables) >= 3 and foreign_keys:
        foreign_refs = [fk_info.get('references') for fk_info in foreign_keys.values() if fk_info.get('references')]
        if len(tables) >= 5 or any(ref in tables for ref in foreign_refs):
            schema_type = 'snowflake'
            warehouse_description = (
                'El esquema del modelo de datos sugiere un enfoque tipo copo de nieve, '
                'con tablas de dimensión normalizadas alrededor de una tabla de hechos.'
            )
        else:
            schema_type = 'star'
            warehouse_description = (
                'El esquema del modelo de datos se presta a un diseño tipo estrella, '
                'con una tabla de hechos central y tablas de dimensión conectadas.'
            )

    tables_without_pk = [t for t, has_pk in table_pk_status.items() if not has_pk]
    data_preparation = []
    if tables_without_pk:
        data_preparation.append(f'Define claves primarias para las tablas: {", ".join(tables_without_pk)}.')
    if json_columns:
        data_preparation.append(
            'Normaliza los datos semi-estructurados (JSON/ARRAY/XML) en tablas relacionales '
            'para facilitar consultas y análisis de BI.'
        )
    if text_columns:
        data_preparation.append(
            'Estandariza y limpia campos de texto libre (TEXT/BLOB) antes de aplicar minería de datos o NLP.'
        )
    if not has_index:
        data_preparation.append(
            'Agrega índices a columnas de búsqueda frecuentes y claves foráneas para mejorar el rendimiento de consultas.'
        )
    data_preparation.append(
        'Verifica la consistencia de nombres de columnas y la calidad de datos con '
        'limpieza de valores nulos/duplicados antes del modelado.'
    )

    data_mining_insights = []
    if schema_type in ['star', 'snowflake']:
        data_mining_insights.append(
            f'El esquema se alinea con un modelo de Data Warehouse tipo {schema_type}. '
            f'Es adecuado para análisis OLAP y minería de datos.'
        )
    if json_columns:
        data_mining_insights.append(
            'El esquema incluye datos semi-estructurados; considera extraer atributos clave y '
            'normalizarlos para facilitar agrupaciones y agregaciones.'
        )
    if text_columns:
        data_mining_insights.append(
            'Hay columnas de texto libre que pueden ser valiosas para minería de texto, '
            'extracción de tópicos y análisis de sentimiento.'
        )
    if not tables_without_pk:
        data_mining_insights.append(
            'Las tablas cuentan con claves primarias definidas, lo cual ayuda a mantener '
            'integridad referencial y soporte para modelos dimensionales.'
        )
    if not data_mining_insights:
        data_mining_insights.append(
            'No se detectaron señales fuertes de minería de datos específica, '
            'pero el esquema es útil para un análisis estructural básico.'
        )

    er_diagram_code = generate_er_diagram_plantuml(tables, table_columns, foreign_keys)
    er_diagram_html = generate_er_diagram_image(er_diagram_code) if er_diagram_code else ''
    snowflake_diagram_code = generate_snowflake_plantuml(tables, table_columns, foreign_keys)
    snowflake_diagram_html = generate_er_diagram_image(snowflake_diagram_code) if snowflake_diagram_code else ''

    ai_summary = ''
    summary_text = 'Análisis completado exitosamente.'
    if tables:
        fk_count = len(foreign_keys)
        pk_count = sum(1 for has_pk in table_pk_status.values() if has_pk)
        summary_text = (
            f'Análisis completado exitosamente. Se detectaron {len(tables)} tabla(s), '
            f'{fk_count} relación(es) FK y {pk_count}/{len(tables)} tabla(s) con clave primaria.'
        )

    try:
        ai_enhancer = AIEnhancer()
        ai_summary = ai_enhancer.enhance_database_analysis(sql_text, {
            'tables': tables,
            'table_columns': table_columns,
            'foreign_keys': foreign_keys,
            'data_sources': {
                'structured': structured,
                'semi_structured': semi_structured,
                'unstructured': unstructured,
            },
            'warehouse_schema': {
                'type': schema_type,
                'description': warehouse_description
            }
        })

        enhanced_sections = ai_enhancer.enhance_database_report_sections({
            'summary': summary_text,
            'data_preparation': data_preparation,
            'data_mining_insights': data_mining_insights,
            'suggestions': suggestions,
            'warehouse_description': warehouse_description,
            'tables': tables,
        })
        if enhanced_sections:
            summary_text = enhanced_sections.get('summary', summary_text)
            data_preparation = enhanced_sections.get('data_preparation', data_preparation)
            data_mining_insights = enhanced_sections.get('data_mining_insights', data_mining_insights)
            suggestions = enhanced_sections.get('suggestions', suggestions)
            warehouse_description = enhanced_sections.get(
                'warehouse_description', warehouse_description
            )
    except Exception as e:
        print(f"[AI DB Summary] {e}")
        if not ai_summary:
            ai_summary = 'Resumen de IA no disponible. Verifica que GROQ_API_KEY esté configurada en .env.'

    return {
        'summary': summary_text,
        'tables': tables,
        'table_columns': table_columns,
        'table_pk_status': table_pk_status,
        'table_primary_keys': table_primary_keys,
        'foreign_keys': foreign_keys,
        'stats': {
            'total_tables': len(tables),
            'fk_relations': len(foreign_keys),
            'tables_with_pk': sum(1 for has_pk in table_pk_status.values() if has_pk),
        },
        'suggestions': suggestions,
        'er_diagram': er_diagram_html,
        'er_diagram_code': er_diagram_code,
        'snowflake_diagram': snowflake_diagram_html,
        'data_sources': {
            'structured': structured,
            'semi_structured': semi_structured,
            'unstructured': unstructured,
        },
        'warehouse_schema': {
            'type': schema_type,
            'description': warehouse_description,
            'diagram_code': snowflake_diagram_code,
        },
        'data_preparation': data_preparation,
        'data_mining_insights': data_mining_insights,
        'ai_summary': ai_summary,
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

    for table in tables:
        columns = table_columns.get(table, [])
        plantuml_code += f'entity "{table}" {{\n'
        for col in columns[:8]:
            plantuml_code += f'  {col["name"]}: {col["type"]}\n'
        if len(columns) > 8:
            plantuml_code += f'  ... ({len(columns) - 8} more columns)\n'
        plantuml_code += "}\n\n"

    for table, fk_info in foreign_keys.items():
        ref_table = fk_info.get('references')
        if ref_table in tables:
            plantuml_code += f'{table} }}--|| {ref_table}\n'

    plantuml_code += "@enduml\n"
    return plantuml_code


def generate_snowflake_plantuml(tables, table_columns, foreign_keys):
    """Genera código PlantUML para un esquema tipo Snowflake."""
    if not tables or not foreign_keys:
        return ''

    reference_counts = {}
    for table in foreign_keys:
        reference_counts[table] = reference_counts.get(table, 0) + 1
    fact_table = max(reference_counts, key=reference_counts.get) if reference_counts else tables[0]
    dimension_tables = [t for t in tables if t != fact_table]

    plantuml_code = "@startuml\n"
    plantuml_code += "skinparam backgroundColor #f1f5f9\n"
    plantuml_code += "skinparam rectangle {\n  BackgroundColor #ffffff\n  BorderColor #0f172a\n  FontColor #0f1418\n}\n\n"
    plantuml_code += f'entity "{fact_table}" as fact <<Fact Table>> {{\n  **Fact Table**\n}}\n\n'

    for idx, dim in enumerate(dimension_tables[:8], start=1):
        plantuml_code += f'entity "{dim}" as dim{idx} <<Dimension>> {{\n  **Dimension**\n}}\n\n'
        plantuml_code += f'fact }}--|| dim{idx} : FK\n'

    dim_refs = {
        table: fk_info.get('references')
        for table, fk_info in foreign_keys.items()
        if table in dimension_tables
    }
    for idx, (dim_table, parent) in enumerate(dim_refs.items(), start=1):
        if parent in dimension_tables:
            plantuml_code += f'entity "{dim_table}_sub" as subdim{idx} <<Sub-Dimension>> {{\n  **Sub-Dimension**\n}}\n\n'
            parent_idx = dimension_tables.index(parent) + 1
            plantuml_code += f'subdim{idx} }}--|| dim{parent_idx} : FK\n'

    plantuml_code += "@enduml\n"
    return plantuml_code


def generate_er_diagram_image(plantuml_code):
    """Genera imagen del diagrama E-R usando PlantUML."""
    try:
        from services.doc_generator import DocGenerator
        from pathlib import Path
        import tempfile

        doc_gen = DocGenerator({})

        with tempfile.NamedTemporaryFile(mode='w', suffix='.puml', delete=False) as f:
            f.write(plantuml_code)
            temp_path = Path(f.name)

        try:
            output_file = temp_path.with_suffix('.png')
            result_path = doc_gen._fetch_plantuml_image(plantuml_code, output_file)
            if result_path and result_path.exists():
                data_uri = doc_gen._image_to_data_uri(result_path)
                if data_uri:
                    return f'<img src="{data_uri}" alt="Diagrama E-R" style="max-width:100%;height:auto;" />'
                result_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[ER Diagram] Error: {e}")
        finally:
            temp_path.unlink(missing_ok=True)

        return (
            f'<pre style="background:#f0f0f0;padding:10px;border-radius:4px;'
            f'font-size:12px;overflow:auto;">{plantuml_code}</pre>'
        )
    except Exception as e:
        print(f"[ER Diagram] Fallback error: {e}")
        return '<p style="color:#999;">No se pudo generar el diagrama E-R.</p>'


@analysis_bp.route('/analyze', methods=['POST'])
@jwt_required()
def analyze_document():
    # Obtener usuario autenticado
    user_id = get_jwt_identity()

    use_ai = request.json.get('use_ai', False)
    
    if use_ai:
        # ... ejecutar análisis con IA ...
        
        # Registrar el uso de IA
        log_usage_manual(
            user_id=user_id,
            action="ai_enhanced",
            metadata={
                "document_id": document_id,
                "project_id": project_id,
            }
        )
    
    # ... resto del código ...