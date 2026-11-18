# Monitoreo y entrega continua · AutoDocs AI

Evidencia para la capacidad: *implementar soluciones de software mediante la integración de componentes de acuerdo a la arquitectura definida para su liberación en un ambiente de producción*.

## 1. Integración continua (CI)

Workflow: `.github/workflows/ci.yml` (GitHub Actions). En cada push y pull request a `main`:

1. Compila el código (`compileall`).
2. Análisis estático con flake8.
3. Pruebas con pytest y reporte de cobertura (`coverage.xml`, `test-results.xml` como artefactos).
4. Construye la imagen Docker.

## 2. Entrega continua (CD) en Render

- Render está conectado al repositorio y despliega automáticamente cada push a `main`.
- El despliegue solo se considera correcto si `GET /health` responde `200` (configurar **Health Check Path = `/health`** en Render → Settings).
- Variable opcional `APP_VERSION` (por ejemplo `v1.0.0`) para que `/health` informe qué versión está en producción.

## 3. Herramientas de monitoreo

| Endpoint | Para qué sirve |
|---|---|
| `GET /health` | Estado del servicio y de MongoDB. `200` = ok, `503` = degradado. Incluye versión y uptime. |
| `GET /metrics` | Métricas en formato Prometheus: uptime, peticiones por método/código, tiempo de respuesta acumulado y errores 5xx. |

Ejemplo de respuesta de `/health`:

```json
{
  "status": "ok",
  "version": "v1.0.0",
  "uptime_seconds": 3600,
  "checks": { "mongodb": { "status": "up", "latency_ms": 4.1 } }
}
```

### Monitores externos (gratuitos)

1. **UptimeRobot**: monitor HTTP a `https://<tu-app>.onrender.com/health` cada 5 minutos, con alerta por correo. También evita que el plan gratuito de Render duerma la app.
2. **Render Metrics** (panel del servicio): CPU, memoria y logs en vivo.
3. **Opcional**: Grafana Cloud (plan gratuito) leyendo `/metrics`.

## 4. Métricas que se reportan

- Disponibilidad (% uptime del monitor externo).
- Tiempo de respuesta promedio = `duration_seconds_sum / duration_seconds_count`.
- Tasa de errores = `errors_5xx_total / requests_total`.
- Cobertura de pruebas (artefacto `coverage.xml` del CI).

> Los contadores de `/metrics` viven en memoria por proceso (gunicorn corre 2 workers) y se reinician con cada despliegue.

## 5. Propuesta de mejoras

1. Persistir métricas con Prometheus + Grafana para tener histórico.
2. Agregar Sentry para capturar excepciones con contexto.
3. Mover las subidas (`uploads/`) y exportaciones a almacenamiento externo (S3 o similar), porque el disco de Render es efímero.
4. Ejecutar un smoke test contra `/health` después de cada despliegue.
5. Subir el umbral de flake8 a reglas de estilo (hoy solo detecta errores graves).
6. Publicar releases etiquetados (`v1.x.x`) con notas de cambios.
