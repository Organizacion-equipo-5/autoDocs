#!/usr/bin/env python
"""
db_setup.py
Script para verificar, diagnosticar y configurar la conexión a MongoDB.

Uso:
    python db_setup.py              # Verificar conexión y crear BD/colecciones
    python db_setup.py --reset      # Reiniciar completamente
    python db_setup.py --check      # Solo verificar conexión
    python db_setup.py --status     # Ver estado actual
"""
import os
import sys
import argparse
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()


def print_header(text):
    """Imprime un encabezado con estilo."""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)


def print_success(text):
    """Imprime mensaje de éxito."""
    print(f"✅  {text}")


def print_error(text):
    """Imprime mensaje de error."""
    print(f"❌  {text}")


def print_info(text):
    """Imprime mensaje informativo."""
    print(f"ℹ️   {text}")


def print_warning(text):
    """Imprime mensaje de advertencia."""
    print(f"⚠️   {text}")


def check_mongodb_connection():
    """Verifica la conexión a MongoDB."""
    print_header("Verificando Conexión a MongoDB")
    
    from app import db
    
    try:
        print_info("Conectando a MongoDB...")
        client, database = db.connect_to_mongodb()
        print_success("Conexión exitosa")
        
        # Obtener información del servidor
        info = client.server_info()
        print_success(f"MongoDB versión: {info.get('version', 'desconocida')}")
        
        # Listar bases de datos
        databases = client.list_database_names()
        print_info(f"Bases de datos en el servidor: {len(databases)}")
        for db_name in databases:
            print(f"   - {db_name}")
        
        return True, client, database
    
    except Exception as e:
        print_error(f"No se pudo conectar: {e}")
        print_info("\n💡 Soluciones posibles:")
        print("   1. Instala MongoDB: https://www.mongodb.com/try/download/community")
        print("   2. Inicia MongoDB: mongod")
        print("   3. Si usas Docker: docker run -d -p 27017:27017 mongo")
        print("   4. Verifica MONGO_URI en .env")
        return False, None, None


def create_collections_and_indexes():
    """Crea colecciones e índices."""
    print_header("Creando Colecciones e Índices")
    
    from app import db
    
    try:
        connected, client, database = check_mongodb_connection()
        if not connected or database is None:
            return False
        
        # Obtener colecciones existentes
        existing = set(database.list_collection_names())
        print_info(f"Colecciones existentes: {len(existing)}")
        
        # Crear colecciones
        for collection_name, config in db.COLLECTIONS.items():
            if collection_name in existing:
                print_info(f"Colección '{collection_name}' ya existe")
            else:
                database.create_collection(collection_name)
                print_success(f"Colección '{collection_name}' creada")
            
            # Crear índices
            collection = database[collection_name]
            for index_config in config.get("indexes", []):
                try:
                    fields = index_config["fields"]
                    unique = index_config.get("unique", False)
                    collection.create_index(fields, unique=unique)
                    print_success(f"  Índice creado en '{collection_name}'")
                except Exception as e:
                    print_warning(f"  Error en índice: {e}")
        
        print_success("Colecciones e índices configurados")
        return True
    
    except Exception as e:
        print_error(f"Error configurando colecciones: {e}")
        return False


def check_environment():
    """Verifica la configuración del entorno."""
    print_header("Verificando Configuración del Entorno")
    
    env_file = Path(".env")
    if not env_file.exists():
        print_warning(".env no encontrado")
        print_info("Creando .env basado en .env.example...")
        env_example = Path(".env.example")
        if env_example.exists():
            env_file.write_text(env_example.read_text())
            print_success(".env creado")
        else:
            print_error(".env.example no encontrado")
            return False
    else:
        print_success(".env encontrado")
    
    # Verificar variables importantes
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB_NAME")
    
    print_info(f"MONGO_URI: {mongo_uri}")
    print_info(f"MONGO_DB_NAME: {mongo_db}")
    
    return True


def reset_database():
    """Reinicia completamente la BD (¡DESTRUCTIVO!)."""
    print_header("⚠️  REINICIO COMPLETO DE LA BASE DE DATOS")
    
    confirm = input("⚠️  Esta acción eliminará TODA la base de datos. ¿Estás seguro? (yes/no): ")
    if confirm.lower() != "yes":
        print_info("Operación cancelada")
        return False
    
    from app import db
    
    try:
        connected, client, database = check_mongodb_connection()
        if not connected or client is None:
            return False
        
        db_name = os.getenv("MONGO_DB_NAME", "meditrack")
        print_warning(f"Eliminando base de datos '{db_name}'...")
        client.drop_database(db_name)
        print_success(f"Base de datos '{db_name}' eliminada")
        
        print_info("Recreando colecciones...")
        # Reconectar para crear nuevas colecciones
        db.client = None
        db.db = None
        db.connect_to_mongodb()
        print_success("Base de datos recreada")
        
        return True
    
    except Exception as e:
        print_error(f"Error al reiniciar: {e}")
        return False


def show_status():
    """Muestra el estado actual."""
    print_header("Estado Actual de MongoDB")
    
    from app import db
    
    try:
        is_connected = db.is_connected()
        if is_connected:
            print_success("MongoDB: Conectado")
            
            database = db.get_db()
            collections = database.list_collection_names()
            print_info(f"Colecciones: {len(collections)}")
            for col in collections:
                count = database[col].count_documents({})
                print(f"   - {col}: {count} documentos")
        else:
            print_error("MongoDB: No conectado")
            print_info("Ejecuta: mongod")
    
    except Exception as e:
        print_error(f"Error: {e}")


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Herramienta de configuración de MongoDB para MediTrack"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reinicia completamente la BD (¡DESTRUCTIVO!)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo verifica la conexión"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Muestra el estado actual"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("  🗄️  MongoDB Setup para MediTrack")
    print("="*60)
    
    try:
        # Verificar ambiente
        if not check_environment():
            return 1
        
        # Ejecutar comando solicitado
        if args.reset:
            if not reset_database():
                return 1
        elif args.check:
            connected, _, _ = check_mongodb_connection()
            if not connected:
                return 1
        elif args.status:
            show_status()
        else:
            # Por defecto: verificar y crear
            connected, _, _ = check_mongodb_connection()
            if not connected:
                return 1
            
            if not create_collections_and_indexes():
                return 1
            
            show_status()
        
        print("\n✨ Operación completada exitosamente\n")
        return 0
    
    except KeyboardInterrupt:
        print("\n\n👋 Operación cancelada por el usuario")
        return 1
    except Exception as e:
        print_error(f"Error inesperado: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
