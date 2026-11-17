"""
routes/chat.py

POST /api/chat/documentation -> Chat de documentación con IA
Permite a los usuarios preguntar sobre la documentación de sus proyectos
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.db import get_db
from services.ai_enhancer import AIEnhancer

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/documentation', methods=['POST'])
@jwt_required()
def documentation_chat():
    """
    Endpoint para el chat de documentación.

    Request body:
    {
        "message": "Pregunta del usuario",
        "project_id": "ID del proyecto (opcional)"
    }

    Response:
    {
        "response": "Respuesta de la IA"
    }
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        project_id = data.get('project_id')

        if not message:
            return jsonify({"error": "Mensaje vacío"}), 400

        user_id = get_jwt_identity()
        db = get_db()

        # Obtener información del proyecto si se proporcionó
        project_context = ""
        if project_id:
            project = db.projects.find_one({"_id": project_id, "user_id": user_id})
            if project:
                project_context = f"Proyecto: {project.get('name', 'sin nombre')}\n"

                # Obtener resultados de análisis si existen
                analysis = db.analysis_results.find_one({"project_id": project_id})
                if analysis:
                    results = analysis.get('results', {})
                    functions = results.get('functions', [])[:5]
                    classes = results.get('classes', [])[:3]
                    endpoints = results.get('endpoints', [])[:3]

                    if functions:
                        project_context += f"\nFunciones principales: {', '.join([f['name'] for f in functions])}"
                    if classes:
                        project_context += f"\nClases principales: {', '.join([c['name'] for c in classes])}"
                    if endpoints:
                        project_context += f"\nEndpoints: {', '.join([e.get('path', '') for e in endpoints])}"

        # Llamar a la IA
        ai = AIEnhancer()
        if not ai.is_available():
            return jsonify({
                "response": "Lo siento, la IA no está configurada. Por favor, contacta al administrador para habilitar la función de chat."
            }), 200

        # Construir el prompt
        system_prompt = """Eres un asistente técnico experto en documentación de software.
Tu objetivo es ayudar a los usuarios a entender la documentación de sus proyectos.
Usa lenguaje claro y profesional. Si no sabes la respuesta, indícalo honestamente."""

        user_prompt = f"""Contexto del proyecto:
{project_context}

Pregunta del usuario:
{message}

Proporciona una respuesta clara y concisa. Si la pregunta requiere información específica del código y no está disponible en el contexto, indícalo."""

        response = ai._call_ai(system_prompt, user_prompt, max_tokens=500)

        if response:
            return jsonify({"response": response}), 200
        else:
            return jsonify({
                "response": "Lo siento, no pude generar una respuesta. Por favor, intenta con otra pregunta."
            }), 200

    except Exception as e:
        import traceback
        print(f"[Chat Error] {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Error al procesar el mensaje"}), 500
