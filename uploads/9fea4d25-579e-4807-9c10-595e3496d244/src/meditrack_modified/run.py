"""
run.py
Punto de entrada de la aplicación MediTrack.

Uso:
    python run.py                  # Modo desarrollo
    FLASK_ENV=production python run.py
"""
import sys
import os
from pathlib import Path

# Configurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from app import create_app, db

def main():
    """Inicializa y ejecuta la aplicación."""
    
    print("\n" + "="*60)
    print("  MediTrack - Sistema de Medicamentos Inteligente")
    print("  Iniciando servidor...")
    print("="*60 + "\n")
    
    try:
        # Verificar que MongoDB está disponible
        print("[*] Verificando conexion a MongoDB...")
        if not db.is_connected():
            print("[X] MongoDB no esta disponible. Intenta:")
            print("   - Instalar MongoDB localmente")
            print("   - Ejecutar: mongod")
            print("   - O configurar MONGO_URI en .env")
            print("\n   Ver: https://www.mongodb.com/docs/manual/installation/")
            sys.exit(1)
        
        print("[+] Conexion a MongoDB verificada\n")
        
        # Crear la aplicación Flask
        app = create_app()
        
        # Configurar puerto y modo debug
        port = int(os.getenv("PORT", 5000))
        debug = os.getenv("FLASK_DEBUG", "True") == "True"
        
        print("="*60)
        print("  Servidor iniciado correctamente!")
        print(f"  [+] Frontend: http://localhost:{port}/")
        print(f"  [+] Health:   http://localhost:{port}/api/v1/health")
        print("  [+] Presiona CTRL+C para detener")
        print("="*60 + "\n")
        
        # Iniciar servidor
        app.run(host="0.0.0.0", port=port, debug=debug)
        
    except KeyboardInterrupt:
        print("\n\n[+] Servidor detenido por el usuario")
        db.close_connection()
        sys.exit(0)
    except Exception as e:
        print(f"\n[X] Error fatal: {e}")
        db.close_connection()
        sys.exit(1)

if __name__ == "__main__":
    main()


