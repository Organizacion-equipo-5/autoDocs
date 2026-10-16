import os
import sys
from pathlib import Path

# Agregar backend al path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.doc_generator import DocGenerator
from services.exporter import DocumentExporter

def main():
    print("=== INICIANDO VALIDACIÓN INTEGRAL DE AUTODOCS ===")

    # 1. Datos simulados de proyecto representativo
    project = {
        "_id": "test_verification_01",
        "name": "AutoDocs Sistema de Gestión y APIs",
    }

    analysis_results = {
        "repo_name": "autoDocs",
        "primary_language": "Python",
        "total_files": 18,
        "directories": {
            "routes": ["api.py", "auth.py"],
            "services": ["ai_enhancer.py", "doc_generator.py", "exporter.py"],
            "models": ["user.py", "project.py", "report.py"],
            "utils": ["helpers.py", "logger.py"],
        },
        "endpoints": [
            {
                "method": "POST",
                "path": "/api/v1/auth/login",
                "file": "routes/auth.py",
                "framework": "Flask",
                "summary": "Autenticación de usuario y retorno de JWT"
            },
            {
                "method": "GET",
                "path": "/api/v1/projects",
                "file": "routes/api.py",
                "framework": "Flask",
                "summary": "Lista todos los proyectos registrados"
            },
            {
                "method": "POST",
                "path": "/api/v1/projects/generate-docs",
                "file": "routes/api.py",
                "framework": "Flask",
                "summary": "Dispara el pipeline de generación de documentación técnica"
            },
            {
                "method": "GET",
                "path": "/api/v1/projects/{id}/export/pdf",
                "file": "routes/api.py",
                "framework": "Flask",
                "summary": "Exporta la documentación generada en formato PDF ejecutivo"
            }
        ],
        "classes": [
            {
                "name": "UserModel",
                "file": "models/user.py",
                "docstring": "Representa las credenciales y perfil de un usuario.",
                "methods": ["verify_password", "to_dict", "generate_auth_token"],
                "bases": ["BaseModel"]
            },
            {
                "name": "ProjectModel",
                "file": "models/project.py",
                "docstring": "",
                "methods": ["save", "delete", "get_by_id"],
                "bases": ["BaseModel"]
            },
            {
                "name": "ReportSchema",
                "file": "models/report.py",
                "docstring": "Esquema de serialización de reportes.",
                "methods": ["validate", "dump"],
                "bases": ["Schema"]
            }
        ],
        "functions": [
            {
                "name": "authenticate_user",
                "file": "routes/auth.py",
                "params": ["username", "password"],
                "is_async": False,
                "complexity": 3,
                "docstring": "Valida credenciales contra la base de datos."
            },
            {
                "name": "build_pdf_report",
                "file": "services/exporter.py",
                "params": ["doc_data", "output_path"],
                "is_async": False,
                "complexity": 6,
                "docstring": ""
            }
        ],
        "quality_score": 88,
    }

    # 2. Generar documentación
    print("\n[Paso 1] Ejecutando DocGenerator (con IA y Kroki PlantUML)...")
    generator = DocGenerator(analysis_results)
    full_docs = generator.generate()

    print(f"-> Documentación Markdown generada: {len(full_docs.get('full_markdown', ''))} caracteres")

    # 3. Exportar a HTML y PDF
    print("\n[Paso 2] Ejecutando DocumentExporter para generar PDF y HTML...")
    full_analysis = {
        "results": analysis_results,
        "documentation": full_docs
    }
    exporter = DocumentExporter(project, full_analysis)

    html_str = exporter.to_html()
    print(f"-> HTML generado: {len(html_str)} caracteres")

    pdf_path_str = exporter.to_pdf()
    pdf_path = Path(pdf_path_str)
    print(f"-> Ruta del PDF generado: {pdf_path}")

    if pdf_path.exists() and pdf_path.stat().st_size > 1000:
        print(f"-> EXCELENTE: PDF generado exitosamente con tamaño {pdf_path.stat().st_size} bytes ({pdf_path.stat().st_size / 1024:.1f} KB)")
    else:
        print(f"-> ERROR: El archivo PDF no existe o es demasiado pequeño.")
        sys.exit(1)

    print("\n=== VALIDACIÓN COMPLETADA CON ÉXITO ===")

if __name__ == "__main__":
    main()
