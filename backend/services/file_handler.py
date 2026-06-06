import os
import zipfile
import tarfile
import subprocess
from pathlib import Path
from werkzeug.utils import secure_filename

UPLOAD_BASE = Path('./uploads')
ALLOWED_EXTENSIONS = {'zip', 'tar', 'gz', 'py', 'js', 'ts', 'java', 'php', 'go', 'rb', 'csv', 'json', 'sql'}

def classify_file_type(filename: str) -> dict:
    """
    Clasifica el tipo de archivo según su contenido potencial.

    Returns:
        dict: {
            'type': 'structured' | 'semi_structured' | 'unstructured',
            'category': str,
            'description': str
        }
    """
    ext = Path(filename).suffix.lower()

    structured = {
        '.sql': {'category': 'database', 'description': 'Archivo SQL - datos estructurados'},
        '.csv': {'category': 'tabular', 'description': 'Archivo CSV - datos tabulares'},
        '.db': {'category': 'database', 'description': 'Base de datos SQLite'},
        '.sqlite': {'category': 'database', 'description': 'Base de datos SQLite'},
        '.sqlite3': {'category': 'database', 'description': 'Base de datos SQLite'},
        '.parquet': {'category': 'analytics', 'description': 'Archivo Parquet - columnar'},
        '.avro': {'category': 'analytics', 'description': 'Archivo Avro - serialización'},
    }

    semi_structured = {
        '.json': {'category': 'document', 'description': 'Archivo JSON - datos semiestructurados'},
        '.xml': {'category': 'document', 'description': 'Archivo XML - datos jerárquicos'},
        '.yaml': {'category': 'config', 'description': 'Archivo YAML - configuración'},
        '.yml': {'category': 'config', 'description': 'Archivo YAML - configuración'},
        '.toml': {'category': 'config', 'description': 'Archivo TOML - configuración'},
        '.ini': {'category': 'config', 'description': 'Archivo INI - configuración'},
        '.py': {'category': 'code', 'description': 'Código Python - semiestructurado'},
        '.js': {'category': 'code', 'description': 'Código JavaScript - semiestructurado'},
        '.ts': {'category': 'code', 'description': 'Código TypeScript - semiestructurado'},
    }

    unstructured = {
        '.txt': {'category': 'text', 'description': 'Archivo de texto plano'},
        '.log': {'category': 'log', 'description': 'Archivo de logs'},
        '.md': {'category': 'documentation', 'description': 'Archivo Markdown'},
        '.rst': {'category': 'documentation', 'description': 'Archivo reStructuredText'},
        '.png': {'category': 'image', 'description': 'Imagen PNG'},
        '.jpg': {'category': 'image', 'description': 'Imagen JPEG'},
        '.jpeg': {'category': 'image', 'description': 'Imagen JPEG'},
        '.gif': {'category': 'image', 'description': 'Imagen GIF'},
        '.bmp': {'category': 'image', 'description': 'Imagen BMP'},
        '.svg': {'category': 'image', 'description': 'Imagen SVG'},
        '.pdf': {'category': 'document', 'description': 'Documento PDF'},
    }

    if ext in structured:
        return {'type': 'structured', **structured[ext]}
    elif ext in semi_structured:
        return {'type': 'semi_structured', **semi_structured[ext]}
    elif ext in unstructured:
        return {'type': 'unstructured', **unstructured[ext]}
    else:
        return {'type': 'unstructured', 'category': 'unknown', 'description': f'Archivo {ext} - tipo desconocido'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clone_github_repo(github_url: str, project_id: str) -> str:
    """Clone a GitHub repository and return the project path."""
    UPLOAD_BASE.mkdir(parents=True, exist_ok=True)
    
    project_dir = UPLOAD_BASE / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove .git extension if present
    repo_name = github_url.rstrip('/').split('/')[-1].replace('.git', '')
    clone_path = project_dir / repo_name
    
    try:
        # Clone the repository with timeout
        result = subprocess.run(
            ['git', 'clone', github_url, str(clone_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120  # 2 minutos timeout
        )
        print(f"[Git Clone] Successfully cloned {github_url} to {clone_path}")
        return str(clone_path.resolve())
    except subprocess.TimeoutExpired:
        print(f"[Git Clone Error] Timeout cloning {github_url}")
        # Remove partial clone if exists
        if clone_path.exists():
            import shutil
            shutil.rmtree(clone_path, ignore_errors=True)
        raise Exception(f"Timeout cloning repository: operation took too long")
    except subprocess.CalledProcessError as e:
        print(f"[Git Clone Error] Command failed with return code {e.returncode}")
        print(f"[Git Clone Error] stdout: {e.stdout}")
        print(f"[Git Clone Error] stderr: {e.stderr}")
        # Remove partial clone if exists
        if clone_path.exists():
            import shutil
            shutil.rmtree(clone_path, ignore_errors=True)
        raise Exception(f"Failed to clone repository: {e.stderr}")
    except Exception as e:
        print(f"[Git Clone Error] Unexpected error: {e}")
        # Remove partial clone if exists
        if clone_path.exists():
            import shutil
            shutil.rmtree(clone_path, ignore_errors=True)
        raise Exception(f"Failed to clone repository: {e}")

def save_uploaded_project(file, project_id: str) -> str:
    """Save uploaded file and extract if archive. Returns project folder path."""
    UPLOAD_BASE.mkdir(parents=True, exist_ok=True)
    
    project_dir = UPLOAD_BASE / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    filename = secure_filename(file.filename)
    file_path = project_dir / filename
    file.save(str(file_path))
    
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if ext == 'zip':
        with zipfile.ZipFile(file_path, 'r') as z:
            z.extractall(project_dir / 'src')
        # Remove the zip file after extraction
        file_path.unlink()
        return str((project_dir / 'src').resolve())
    elif ext in ('tar', 'gz'):
        with tarfile.open(file_path, 'r:*') as t:
            t.extractall(project_dir / 'src')
        # Remove the tar file after extraction
        file_path.unlink()
        return str((project_dir / 'src').resolve())
    else:
        return str(project_dir.resolve())
