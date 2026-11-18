# Plan de trabajo · Liberación y monitoreo (AutoDocs AI)

**Objetivo:** liberar AutoDocs AI en producción (Render) mediante entrega continua y monitorearlo.
**Fecha de entrega final:** 5 de diciembre de 2026.

| # | Actividad | Entregable | Fecha límite |
|---|---|---|---|
| 1 | Configurar ambiente de liberación en Render (variables de entorno, MongoDB, Health Check Path `/health`) | Servicio en línea | 20 nov 2026 |
| 2 | Automatizar compilación y pruebas (GitHub Actions) | `ci.yml` con ejecuciones en verde | 21 nov 2026 |
| 3 | Automatizar el despliegue (Render, auto-deploy desde `main`) | Despliegue por cada push | 22 nov 2026 |
| 4 | Implementar monitoreo (`/health`, `/metrics`, UptimeRobot) | Monitores activos y alertas | 24 nov 2026 |
| 5 | Evaluar rendimiento y disponibilidad (7 días de datos) | Métricas de uptime y latencia | 1 dic 2026 |
| 6 | Manuales y documentación (README, `docs/MONITOREO.md`, QA_REPORT) | Documentación en el repositorio | 2 dic 2026 |
| 7 | Versionamiento: release `v1.0.0` con notas de cambios | Tag y release en GitHub | 3 dic 2026 |
| 8 | Propuesta de mejoras y entrega final | Software desplegado, pipeline, pruebas, monitoreo, métricas y propuesta de mejora | 5 dic 2026 |

## Responsables

Equipo 5 (completar con nombre de cada integrante por actividad).

## Riesgos

- El plan gratuito de Render duerme la app tras inactividad → mitigado con UptimeRobot.
- El disco de Render es efímero → las subidas se pierden al redesplegar (ver propuesta de mejoras).
