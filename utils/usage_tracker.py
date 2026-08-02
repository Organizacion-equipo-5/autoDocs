"""
utils/usage_tracker.py
Helpers para registrar uso de IA y exportaciones usando tu sistema de DB
"""

from datetime import datetime
from flask import request, g
from functools import wraps
from services.db import get_db
from services.plan_recommender import log_usage


def track_usage(action_name):
    """
    Decorator para registrar automáticamente el uso de IA o exportaciones.
    
    Uso:
        @track_usage("ai_enhanced")
        def enhanced_analysis():
            ...
    
    O:
        @track_usage("export_pdf")
        def export_pdf():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Ejecutar la función primero
            result = f(*args, **kwargs)
            
            try:
                db = get_db()
                
                # Obtener user_id de diferentes fuentes posibles
                user_id = None
                if hasattr(g, 'user_id'):
                    user_id = g.user_id
                elif len(args) > 0 and hasattr(args[0], 'user_id'):
                    user_id = args[0].user_id
                elif 'user_id' in kwargs:
                    user_id = kwargs['user_id']
                
                if user_id:
                    log_usage(db, user_id, action_name, {
                        "endpoint": request.endpoint,
                        "method": request.method,
                    })
            except Exception as e:
                print(f"⚠️ Error registrando uso {action_name}: {e}")
            
            return result
        return decorated_function
    return decorator


def log_usage_manual(user_id: str, action: str, metadata: dict = None):
    """
    Función manual para registrar uso desde cualquier parte del código.
    
    Args:
        user_id: ID del usuario
        action: "ai_enhanced", "export_pdf", "export_html", "export_markdown"
        metadata: datos adicionales (opcional)
    
    Ejemplo:
        from utils.usage_tracker import log_usage_manual
        
        def mi_funcion(user_id):
            # ... hacer algo ...
            log_usage_manual(user_id, "ai_enhanced", {"document_id": doc_id})
    """
    try:
        db = get_db()
        return log_usage(db, user_id, action, metadata)
    except Exception as e:
        print(f"⚠️ Error en log_usage_manual: {e}")
        return False