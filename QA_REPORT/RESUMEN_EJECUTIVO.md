# Resumen ejecutivo — AutoDocs backend

Fecha: 2026-11-16.

Se ejecutó `python -m pytest -p no:cacheprovider -q` en `tests/test_*.py`, sin API/MongoDB. **304 pruebas: 303 aprobadas, 1 fallida.** Falló `tests/test_exporter.py::TestRenderMarkdownWithNode::test_script_no_existe_lanza_error`: en Windows la ruta mock `MagicMock` llega a `subprocess.run` y causa `NotADirectoryError` antes de la excepción esperada. Es un fallo del test/mock reproducido; no demuestra por sí mismo un defecto de producción.

No se ejecutaron flujos API, UI, seguridad dinámica ni carga. Docker engine no está disponible y el compose apunta a `./backend`, aunque el repositorio examinado ya contiene `app.py` y `Dockerfile` en su raíz. No se modificó código fuente.

Riesgos estáticos: credencial MongoDB como valor predeterminado en `config.py` (alto, rotar si activa y retirar del código); `DEBUG=True` si falta `FLASK_DEBUG` (alto condicionado al despliegue); CORS `*` para `/api/*` (medio condicionado al despliegue).
