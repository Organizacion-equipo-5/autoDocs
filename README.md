# AutoDocs AI 🤖📄

> Plataforma inteligente de documentación automática para proyectos de software.

## Descripción

AutoDocs AI analiza automáticamente proyectos de software y genera documentación técnica profesional. El sistema detecta funciones, clases, endpoints API y calcula métricas de calidad del código.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.12 + Flask 3.0 |
| Frontend | HTML5 + CSS3 + JavaScript Vanilla |
| Base de datos | MongoDB 7 |
| Autenticación | JWT (Flask-JWT-Extended) |
| Análisis | Python AST + Regex |
| Exportación | WeasyPrint (PDF) + Markdown |
| Contenedores | Docker + Docker Compose |

## Arquitectura

```
autodocs-ai/
├── backend/
│   ├── app.py              # Entrypoint Flask
│   ├── config.py           # Configuración
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── routes/
│   │   ├── web.py          # Rutas HTML (SSR)
│   │   ├── auth.py         # /api/auth/*
│   │   ├── projects.py     # /api/projects/*
│   │   ├── analysis.py     # /api/analysis/*
│   │   └── export.py       # /api/export/*
│   └── services/
│       ├── db.py           # Conexión MongoDB
│       ├── analyzer.py     # Motor AST de análisis
│       ├── doc_generator.py # Generador de docs
│       ├── file_handler.py  # Manejo de archivos
│       └── exporter.py     # PDF/Markdown/HTML
├── frontend/
│   ├── templates/
│   │   ├── index.html      # Landing page
│   │   ├── dashboard.html  # Dashboard principal
│   │   └── analysis.html   # Vista de análisis
│   └── static/
│       ├── css/
│       ├── js/
│       └── assets/
├── docker-compose.yml
└── README.md
```

## Instalación Rápida

### Con Docker (Recomendado)

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/autodocs-ai.git
cd autodocs-ai

# Levantar todos los servicios
docker compose up -d

# Acceder en http://localhost:5000
```

### Sin Docker (Desarrollo local)

```bash
# 1. Instalar dependencias Python
cd backend
pip install -r requirements.txt

# 2. Iniciar MongoDB local
mongod --dbpath /data/db

# 3. Variables de entorno
export MONGO_URI="mongodb://localhost:27017/autodocs_ai"
export SECRET_KEY="tu-clave-secreta"
export JWT_SECRET_KEY="tu-jwt-secreto"

# 4. Iniciar la app
python app.py
```

## API Reference

### Autenticación

```
POST /api/auth/register   - Registrar usuario
POST /api/auth/login      - Iniciar sesión
GET  /api/auth/me         - Perfil del usuario
```

### Proyectos

```
GET    /api/projects/           - Listar proyectos
POST   /api/projects/           - Crear proyecto (multipart/form-data)
GET    /api/projects/:id        - Obtener proyecto
DELETE /api/projects/:id        - Eliminar proyecto
```

### Análisis

```
POST /api/analysis/:id/start    - Iniciar análisis (async)
GET  /api/analysis/:id/results  - Obtener resultados
GET  /api/analysis/:id/status   - Estado del análisis
```

### Exportación

```
GET /api/export/:id/pdf         - Exportar PDF
GET /api/export/:id/markdown    - Exportar Markdown
GET /api/export/:id/html        - Exportar HTML
```

## Funcionalidades

- ✅ Análisis estático de código con Python AST
- ✅ Detección de endpoints Flask, FastAPI, Express.js
- ✅ Generación automática de README
- ✅ Score de calidad con complejidad ciclomática
- ✅ Exportación PDF/Markdown/HTML
- ✅ Autenticación JWT
- ✅ Análisis asíncrono en background
- ✅ Soporte multi-lenguaje (Python, JS, TS, Java, PHP, Go, Ruby, C#, Rust...)
- ✅ Dashboard web responsive

## Lenguajes Soportados

Python, JavaScript, TypeScript, Java, PHP, Go, Ruby, C#, C++, C, Rust, Swift, Kotlin

## Contribuir

1. Fork el repositorio
2. Crea una rama: `git checkout -b feature/nueva-funcionalidad`
3. Commit: `git commit -m 'feat: agregar nueva funcionalidad'`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Abre un Pull Request

## Licencia

MIT — ver [LICENSE](LICENSE)
