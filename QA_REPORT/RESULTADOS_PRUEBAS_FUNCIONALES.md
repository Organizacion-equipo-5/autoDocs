# Resultados funcionales — backend

- Suite automatizada: 304 recogidas, 303 pass, 1 fail. Log resumido: `logs/execution_summary.log`.
- No se probaron registro/login, CRUD con DB, análisis real, API, pagos ni exportación vía servidor.
- Fallo: `test_exporter.py::TestRenderMarkdownWithNode::test_script_no_existe_lanza_error`; el mock fuerza una ruta inválida y Windows lanza `NotADirectoryError` al iniciar Node. Reproducir con `python -m pytest -p no:cacheprovider -q` desde la raíz.
- Sin capturas: no se inició una UI.
