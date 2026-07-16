"""
app/db.py
Configuración centralizada de la conexión a MongoDB.
Conexión automática a MongoDB y creación de colecciones si no existen.
"""
import logging
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Variables globales
client = None
db = None

# Diccionario con las colecciones necesarias del proyecto
COLLECTIONS = {
    "users": {
        "indexes": [
            {"fields": [("email", ASCENDING)], "unique": True},
            {"fields": [("rol", ASCENDING)], "unique": False},
        ]
    },
    "medications": {
        "indexes": [
            {"fields": [("adulto_id", ASCENDING), ("activo", ASCENDING)], "unique": False},
        ]
    },
    "medication_logs": {
        "indexes": [
            {"fields": [("adulto_id", ASCENDING), ("hora_programada", DESCENDING)], "unique": False},
            {"fields": [("medicamento_id", ASCENDING), ("hora_programada", DESCENDING)], "unique": False},
        ]
    },
    "iot_devices": {
        "indexes": [
            {"fields": [("adulto_id", ASCENDING)], "unique": False},
        ]
    },
    "iot_readings": {
        "indexes": [
            {"fields": [("device_id", ASCENDING), ("timestamp", DESCENDING)], "unique": False},
            {"fields": [("adulto_id", ASCENDING), ("alerta", ASCENDING)], "unique": False},
        ]
    },
    "notifications": {
        "indexes": [
            {"fields": [("destinatario_id", ASCENDING), ("leida", ASCENDING)], "unique": False},
        ]
    },
}


def connect_to_mongodb():
    """
    Conecta a MongoDB y crea automáticamente la BD y colecciones si no existen.
    """
    global client, db
    
    try:
        # Obtener URI de MongoDB desde variables de entorno
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        db_name = os.getenv("MONGO_DB_NAME", "meditrack")
        
        logger.info(f"🔄 Intentando conectar a MongoDB: {mongo_uri}")
        
        # Crear cliente con timeout de 5 segundos
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=5000
        )
        
        # Probar la conexión
        client.server_info()
        logger.info("✅ Conexión a MongoDB exitosa")
        
        # Obtener/crear la base de datos
        db = client[db_name]
        logger.info(f"✅ Base de datos '{db_name}' lista")
        
        # Crear colecciones y sus índices
        _create_collections_and_indexes(db)
        
        return client, db
    
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        logger.critical(f"❌ CRITICAL: No se pudo conectar a MongoDB: {e}")
        logger.critical("⚠️  Asegúrate de que MongoDB está corriendo (mongodb://localhost:27017/)")
        
        # Variables en None para evitar errores en los módulos que importen db
        client = None
        db = None
        raise
    
    except Exception as e:
        logger.critical(f"❌ CRITICAL: Error inesperado conectando a MongoDB: {e}")
        client = None
        db = None
        raise


def _create_collections_and_indexes(database):
    """
    Crea las colecciones y sus índices si no existen.
    
    Args:
        database: Instancia de la base de datos MongoDB
    """
    try:
        # Obtener colecciones existentes
        existing_collections = set(database.list_collection_names())
        
        for collection_name, config in COLLECTIONS.items():
            # Crear colección si no existe
            if collection_name not in existing_collections:
                database.create_collection(collection_name)
                logger.info(f"✅ Colección '{collection_name}' creada")
            else:
                logger.info(f"ℹ️  Colección '{collection_name}' ya existe")
            
            # Crear índices para la colección
            collection = database[collection_name]
            for index_config in config.get("indexes", []):
                try:
                    fields = index_config["fields"]
                    unique = index_config.get("unique", False)
                    
                    collection.create_index(fields, unique=unique)
                    logger.info(f"✅ Índice creado en '{collection_name}' para campos: {fields}")
                except Exception as e:
                    logger.warning(f"⚠️  Error creando índice en '{collection_name}': {e}")
        
        logger.info("✅ Todas las colecciones e índices están listos")
    
    except Exception as e:
        logger.error(f"❌ Error creando colecciones e índices: {e}")
        raise


def get_db():
    """
    Retorna la instancia de la base de datos.
    Si no está conectada, intenta conectar.
    """
    global client, db
    
    if db is None:
        connect_to_mongodb()
    
    return db


def get_client():
    """Retorna el cliente de MongoDB."""
    global client
    
    if client is None:
        connect_to_mongodb()
    
    return client


def close_connection():
    """Cierra la conexión a MongoDB."""
    global client, db
    
    if client:
        client.close()
        logger.info("✅ Conexión a MongoDB cerrada")
        client = None
        db = None


def is_connected():
    """Verifica si está conectado a MongoDB. Si no lo está, intenta conectar."""
    global client, db
    
    # Si ya estamos conectados, verifica la conexión
    if client is not None and db is not None:
        try:
            client.server_info()
            return True
        except Exception:
            return False
    
    # Si no estamos conectados, intenta conectar
    try:
        connect_to_mongodb()
        return True
    except Exception:
        return False
