# Integración con GitHub

AutoDocs se conecta con GitHub de dos formas que se pueden usar por separado o juntas:

| | **GitHub Action** | **Webhook** |
|---|---|---|
| Dónde corre | Dentro del CI del repositorio analizado | En el servidor de AutoDocs |
| Qué hace | Compara la rama base con el PR y **comenta el cambio del score**; genera `docs/AUTODOCS.md` | **Regenera el análisis** del proyecto en AutoDocs en cada push a la rama principal |
| Necesita | Nada (solo librería estándar de Python) | `GITHUB_WEBHOOK_SECRET` en el servidor y un proyecto creado desde la URL del repo |
| Resultado | Comentario en el PR, resumen del job, archivo Markdown | Nuevo análisis en el historial del proyecto (Insights → Comparar versiones) |

## 1. GitHub Action

### Comentario de calidad en cada PR

```yaml
# .github/workflows/autodocs-pr.yml
name: AutoDocs — calidad del PR
on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # necesario para leer el commit base
      - uses: Organizacion-equipo-5/autoDocs@main
        with:
          command: pr
          fail-under: 60          # opcional: falla si el score es menor
          max-drop: 5             # opcional: falla si baja más de 5 puntos
```

El comentario incluye el score antes y después, endpoints, clases y funciones nuevas o eliminadas, funciones
nuevas con complejidad alta, y el cambio en código muerto, líneas duplicadas y archivos "calientes". Si el PR
se actualiza, el mismo comentario se edita (no se crean comentarios nuevos). Siempre se escribe también en el
resumen del job.

> **PRs desde forks:** GitHub entrega un token de solo lectura, así que no se puede comentar. La acción no
> falla por eso: muestra un aviso y deja el reporte en el resumen del job.

### Regenerar la documentación en cada push

```yaml
# .github/workflows/autodocs-docs.yml
on:
  push:
    branches: [main]
    paths-ignore: ['docs/AUTODOCS.md']   # evita bucles si se versiona el archivo
permissions:
  contents: write
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Organizacion-equipo-5/autoDocs@main
        with:
          command: docs
          output: docs/AUTODOCS.md
      - name: Versionar la documentación
        run: |
          git config user.name  "autodocs-bot"
          git config user.email "autodocs-bot@users.noreply.github.com"
          git add docs/AUTODOCS.md
          git diff --cached --quiet || (git commit -m "docs: actualizar documentación automática [skip ci]" && git push)
```

### Entradas y salidas

| Entrada | Por defecto | Descripción |
|---|---|---|
| `command` | `pr` | `pr` (comparar y comentar) o `docs` (generar Markdown) |
| `path` | `.` | Carpeta del proyecto |
| `fail-under` | — | Score mínimo aceptado (solo `pr`) |
| `max-drop` | — | Caída máxima de score aceptada (solo `pr`) |
| `comment` | `true` | `false` para no comentar (solo `pr`) |
| `ignore` | — | Carpetas a excluir por nombre, separadas por comas (`docs,examples`) |
| `output` | `docs/AUTODOCS.md` | Archivo a generar (solo `docs`) |
| `github-token` | `github.token` | Token para comentar |

Salidas: `score`, `base-score`, `delta`.

### Usarlo sin Action (cualquier CI)

```bash
python scripts/autodocs_ci.py pr --path . --fail-under 60 --max-drop 5
python scripts/autodocs_ci.py analyze --path . --out snapshot.json
python scripts/autodocs_ci.py report --snapshot snapshot.json --out docs/AUTODOCS.md
```

## 2. Webhook (regenerar en el servidor de AutoDocs)

1. Define una variable de entorno en el servidor con un secreto largo y aleatorio, por ejemplo con
   `openssl rand -hex 32`:

   ```bash
   GITHUB_WEBHOOK_SECRET=<el_secreto>
   ```

2. En GitHub: **Settings → Webhooks → Add webhook**
   - **Payload URL:** `https://TU-SERVIDOR/api/integrations/github/webhook`
   - **Content type:** `application/json`
   - **Secret:** el mismo valor
   - **Events:** *Just the push event*

3. Crea (o reutiliza) un proyecto en AutoDocs **desde la URL del repositorio**.

Comportamiento:

- Cada petición se valida con la firma `X-Hub-Signature-256` (HMAC-SHA256). Sin secreto configurado el
  endpoint responde `503`; con firma inválida, `401`.
- Solo se procesan pushes a la **rama principal** del repositorio. Otros eventos y ramas se ignoran (`202`).
- Se actualiza el clon del proyecto, se vuelve a analizar y se guarda un nuevo análisis en el historial con el
  commit que lo originó. Se respetan el límite mensual de análisis del plan y se omite un proyecto que ya se
  esté analizando.
- Solo funciona con repositorios que el servidor pueda clonar (públicos).

## 3. Ver los resultados en la aplicación

En la página de análisis de un proyecto, el botón **Insights** abre:

- **Salud del código:** código muerto, bloques duplicados y mapa de calor de complejidad por archivo.
- **Comparar versiones:** gráfica de la tendencia del score y comparación entre dos análisis (qué funciones,
  clases y endpoints se agregaron, cambiaron, se movieron o desaparecieron).
- **Chat con la documentación:** preguntas en lenguaje natural sobre el proyecto
  (p. ej. «¿dónde se valida el login?»). Con plan que incluya IA, la respuesta se redacta con Groq/Ollama a
  partir de los fragmentos recuperados; sin IA se muestran los fragmentos encontrados con su ubicación.

API: `GET /api/insights/<id>/health`, `GET /api/insights/<id>/history`,
`GET /api/insights/<id>/compare?from=&to=`, `POST /api/insights/<id>/chat`.

## Limitaciones conocidas

- El **código muerto** se detecta por nombre (una función cuyo nombre no aparece en ningún otro lugar del
  proyecto). Es conservador, pero revisa cada caso antes de borrar. No se analizan Java, C#, Kotlin, Swift ni
  Scala porque las interfaces y la herencia lo vuelven poco fiable.
- En lenguajes distintos de Python la complejidad del mapa de calor es una **estimación** (conteo de ramas).
- El mapa de calor **no incluye archivos de prueba** (`tests/`, `test_*.py`, `*.spec.js`…) y en el chat el código de
  pruebas pesa menos que el de la aplicación.
- El score de calidad es el mismo que ya calcula AutoDocs (documentación, complejidad, errores y pruebas).
