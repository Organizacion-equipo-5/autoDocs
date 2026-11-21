# backend/tests/conftest.py
import sys
import os

# Las pruebas no necesitan secretos reales: config.py genera claves aleatorias si TESTING esta activo.
os.environ.setdefault("TESTING", "1")

# Agrega el directorio 'backend' al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))