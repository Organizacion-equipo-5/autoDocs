# Recomendaciones — backend

1. Revocar/rotar la credencial MongoDB y retirarla de defaults; manejarla por entorno.
2. Fijar `FLASK_DEBUG=False` en producción y restringir CORS.
3. Corregir la ruta del build de Docker Compose y levantar MongoDB local desechable.
4. Reparar el test de exportación para usar ruta temporal real o mockear `subprocess.run`; repetir suite.
5. Probar auth, aislamiento de proyectos y controles por propietario con dos cuentas sintéticas en staging.
6. Ejecutar k6 gradual en staging/local, guardar métricas reales y logs de servidor.
