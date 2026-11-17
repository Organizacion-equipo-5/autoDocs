# Errores y hallazgos — backend

| ID | Prioridad | Estado | Hallazgo |
|---|---|---|---|
| B-01 | Alto | Riesgo estático | Credencial MongoDB como default en config.py; rotar y eliminar del código |
| B-02 | Alto | Condicionado al entorno | DEBUG activo si falta configuración; validar despliegue |
| B-03 | Medio | Condicionado al entorno | CORS permite cualquier origen en /api/* |
| B-04 | Bajo | Confirmado en suite | Test de exportador falla por mock/ruta inválida en Windows (303/304 pasan) |

No se confirmó exposición de datos ni error crítico de ejecución.
