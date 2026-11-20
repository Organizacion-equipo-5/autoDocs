#services/analyzer.py
import os
import ast
import re
from pathlib import Path
from collections import defaultdict


class ProjectAnalyzer:
    """
    Analiza un proyecto completo y extrae información estructural y técnica.

    Este script se usa para:
    - recorrer el árbol de archivos del proyecto
    - detectar el lenguaje dominante
    - extraer funciones, clases y endpoints
    - calcular métricas de calidad

    Los resultados se consumen luego por DocGenerator para generar la documentación.
    """

    LANGUAGE_EXTENSIONS = {
        # Web / scripting
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
        '.jsx': 'React (JSX)', '.tsx': 'React (TSX)',
        '.php': 'PHP', '.rb': 'Ruby', '.pl': 'Perl', '.lua': 'Lua',
        # Systems
        '.c': 'C', '.h': 'C/C++ Header', '.cpp': 'C++', '.cc': 'C++', '.cxx': 'C++',
        '.cs': 'C#', '.rs': 'Rust', '.go': 'Go', '.zig': 'Zig', '.nim': 'Nim',
        # JVM
        '.java': 'Java', '.kt': 'Kotlin', '.kts': 'Kotlin',
        '.scala': 'Scala', '.groovy': 'Groovy', '.clj': 'Clojure',
        # Mobile
        '.swift': 'Swift', '.m': 'Objective-C', '.dart': 'Dart',
        # Functional
        '.hs': 'Haskell', '.elm': 'Elm',
        '.ex': 'Elixir', '.exs': 'Elixir', '.erl': 'Erlang',
        '.ml': 'OCaml', '.fs': 'F#', '.fsx': 'F#',
        # Data / scientific
        '.r': 'R', '.jl': 'Julia',
        '.sql': 'SQL', '.psql': 'SQL',
        # Shell
        '.sh': 'Shell', '.bash': 'Bash', '.zsh': 'Zsh',
        '.ps1': 'PowerShell', '.bat': 'Batch',
        # Frontend / markup
        '.html': 'HTML', '.htm': 'HTML', '.css': 'CSS',
        '.scss': 'SCSS', '.sass': 'Sass', '.less': 'LESS',
        '.xml': 'XML', '.yaml': 'YAML', '.yml': 'YAML',
        '.json': 'JSON', '.toml': 'TOML', '.ini': 'INI',
        # Infra
        '.tf': 'Terraform', '.hcl': 'HCL',
        # Other
        '.proto': 'Protobuf', '.graphql': 'GraphQL', '.gql': 'GraphQL',
        '.sol': 'Solidity', '.coffee': 'CoffeeScript',
        '.v': 'Verilog', '.sv': 'SystemVerilog',
    }

    DEEP_ANALYSIS_LANGS = {
        'Python', 'JavaScript', 'TypeScript', 'React (JSX)', 'React (TSX)',
        'Java', 'PHP', 'Ruby', 'Go', 'Rust', 'C#', 'Kotlin', 'Swift',
        'C', 'C++', 'C/C++ Header', 'Elixir', 'Scala',
    }

    IGNORE_DIRS = {
        # Version control / IDE
        '.git', '.github', '.gitlab', '.idea', '.vscode',
        # Python
        '__pycache__', '.venv', 'venv', 'env', '.pytest_cache', '.mypy_cache',
        # JS / TS
        'node_modules', 'bower_components', '.next', '.nuxt',
        # Build output
        'dist', 'build', 'target', 'coverage', 'vendor',
        # DB migrations
        'migrations',
        # Test dirs
        'tests', 'test', 'spec', '__tests__', 'cypress', 'e2e',
        # Binary/generated asset dirs (not source code)
        'media', 'images', 'fonts',
        'tmp', 'temp', '.cache',
    }

    # Ignorar archivos grandes y archivos de prueba (valores desde config)
    MAX_FILE_SIZE = 500 * 1024  # 500KB - puede sobrescribirse desde config
    MAX_FILES = 300  # máximo de archivos a analizar
    IGNORE_FILE_PATTERNS = {
        'test', 'spec', 'mock', 'fixture', '__pycache__',
        '.min.js', '.min.css', 'bundle.js', 'webpack',
    }

    # Extensiones binarias/generadas que nunca deben analizarse como código
    IGNORE_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
        '.pdf', '.zip', '.tar', '.gz', '.tgz', '.rar', '.7z',
        '.exe', '.dll', '.so', '.dylib', '.bin', '.wasm',
        '.pyc', '.pyo', '.pyd', '.class', '.o', '.obj',
        '.db', '.sqlite', '.sqlite3',
        '.lock',  # package-lock.json is handled by name, but *.lock files skip
        '.puml',  # PlantUML source files in exports/
    }

    def __init__(self, project_path: str):
        if not project_path:
            raise ValueError("project_path no puede ser None o vacío")

        p = Path(project_path)
        try:
            p = p.resolve()
        except Exception:
            p = Path(project_path)

        if p.exists() and p.is_file():
            suffix = p.suffix.lower()
            if suffix in {'.zip', '.tar', '.gz', '.tgz', '.tar.gz'}:
                try:
                    import zipfile, tarfile
                    dest = p.parent / 'src'
                    dest.mkdir(parents=True, exist_ok=True)
                    if suffix == '.zip':
                        with zipfile.ZipFile(p, 'r') as z:
                            z.extractall(dest)
                    else:
                        with tarfile.open(p, 'r:*') as t:
                            t.extractall(dest)
                    p = dest.resolve()
                except Exception:
                    p = p.parent
            else:
                p = p.parent

        if not p.exists():
            raise ValueError(f"La ruta del proyecto no existe: {project_path}")

        if not p.is_dir():
            raise ValueError(f"La ruta no es un directorio: {project_path}")

        self.project_path = p
        self.results = {
            "total_files": 0, "primary_language": "unknown",
            "languages": {}, "structure": [], "functions": [],
            "classes": [], "models": [], "endpoints": [], "imports": [],
            "quality_score": 0, "complexity": {}, "issues": [],
            "project_path": str(self.project_path)
        }

    def analyze(self) -> dict:
        """
        Ejecuta el pipeline completo de análisis.

        1. Recorre el proyecto y detecta archivos/lenguajes.
        2. Calcula el lenguaje principal.
        3. Extrae funciones, clases y endpoints según el lenguaje.
        4. Calcula la puntuación de calidad del proyecto.
        """
        if not self.project_path.exists():
            self.results["error"] = "Project path does not exist"
            return self.results

        # Paso 1: construir la estructura y contar lenguajes.
        self._scan_structure()

        # Paso 2: identificar el lenguaje dominante del proyecto.
        self._detect_primary_language()

        # Paso 3: analizar archivos relevantes para extraer funciones y endpoints.
        self._analyze_code_files()

        # Paso 4: calcular métricas agregadas de calidad.
        self._calculate_quality_score()
        return self.results

    def _scan_structure(self):
        """
        Recorre todos los archivos del proyecto y guarda:
        - ruta relativa
        - nombre
        - extensión
        - lenguaje inferido
        - tamaño
        - líneas físicas de código

        Solo guarda un máximo de 300 archivos para no cargar demasiado la respuesta.
        Ignora archivos grandes (> 500KB) y archivos de prueba.
        """
        structure = []
        lang_count = defaultdict(int)
        total = 0
        max_files = 300
        files_processed = 0

        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            rel_root = Path(root).relative_to(self.project_path)

            for fname in files:
                # Limitar a 300 archivos para optimizar
                if files_processed >= max_files:
                    break

                full_path = Path(root) / fname
                ext = Path(fname).suffix.lower()

                # Ignorar extensiones binarias/generadas
                if ext in self.IGNORE_EXTENSIONS:
                    continue

                # Ignorar archivos de prueba y minificados
                fname_lower = fname.lower()
                if any(pattern in fname_lower for pattern in self.IGNORE_FILE_PATTERNS):
                    continue

                # Ignorar archivos grandes
                try:
                    size = os.path.getsize(full_path)
                    if size > self.MAX_FILE_SIZE:
                        continue
                except OSError:
                    size = 0
                    continue

                lang = self.LANGUAGE_EXTENSIONS.get(ext)
                if not lang and full_path.exists():
                    lang = self._guess_language_by_shebang(full_path)

                try:
                    with full_path.open('r', encoding='utf-8', errors='ignore') as source_file:
                        line_count = sum(1 for _ in source_file)
                except Exception as error:
                    print(f"[Analyzer] No se pudieron contar líneas en {full_path}: {error}")
                    try:
                        line_count = len(full_path.read_bytes().split(b'\n'))
                    except Exception:
                        line_count = 0

                if lang:
                    lang_count[lang] += 1
                    total += 1

                structure.append({
                    "path": str(rel_root / fname), "name": fname, "type": "file",
                    "language": lang or "other", "size": size, "extension": ext,
                    "line_count": line_count,
                })
                files_processed += 1

        self.results["structure"] = structure[:max_files]
        self.results["total_files"] = total
        self.results["languages"] = dict(lang_count)

    def _detect_primary_language(self):
        """
        Elige el lenguaje principal del proyecto.

        Se excluyen archivos de configuración (JSON, YAML, HTML, CSS, etc.)
        para que el lenguaje dominante refleje el código real del proyecto.
        """
        config_langs = {'JSON', 'YAML', 'TOML', 'INI', 'XML', 'HTML', 'CSS',
                        'SCSS', 'Sass', 'LESS', 'SQL', 'C/C++ Header'}
        langs = {k: v for k, v in self.results["languages"].items() if k not in config_langs}
        if langs:
            self.results["primary_language"] = max(langs, key=langs.get)
        elif self.results["languages"]:
            self.results["primary_language"] = max(self.results["languages"], key=self.results["languages"].get)

    def _guess_language_by_shebang(self, filepath: Path):
        try:
            first_line = filepath.read_text(encoding='utf-8', errors='ignore').splitlines()[0].strip()
        except Exception:
            return None
        if first_line.startswith('#!'):
            if 'python' in first_line:
                return 'Python'
            if 'node' in first_line or 'nodejs' in first_line:
                return 'JavaScript'
            if 'bash' in first_line or 'sh' in first_line:
                return 'Shell'
            if 'ruby' in first_line:
                return 'Ruby'
            if 'perl' in first_line:
                return 'Perl'
            if 'php' in first_line:
                return 'PHP'
            if 'lua' in first_line:
                return 'Lua'
            if 'dart' in first_line:
                return 'Dart'
            if 'pwsh' in first_line or 'powershell' in first_line:
                return 'PowerShell'
        return None

    def _analyze_code_files(self):
        """
        Selecciona el analizador correcto para cada archivo detectado.

        El diccionario `dispatch` mapea el lenguaje a su función específica,
        evitando tener que hacer ifs repetitivos para cada archivo.
        """
        dispatch = {
            'Python': self._analyze_python_file,
            'JavaScript': self._analyze_js_ts_file,
            'TypeScript': self._analyze_js_ts_file,
            'React (JSX)': self._analyze_js_ts_file,
            'React (TSX)': self._analyze_js_ts_file,
            'Java': self._analyze_java_file,
            'PHP': self._analyze_php_file,
            'Ruby': self._analyze_ruby_file,
            'Go': self._analyze_go_file,
            'C#': self._analyze_csharp_file,
            'Kotlin': self._analyze_kotlin_file,
            'Rust': self._analyze_rust_file,
            'Swift': self._analyze_swift_file,
            'C': self._analyze_c_cpp_file,
            'C++': self._analyze_c_cpp_file,
            'C/C++ Header': self._analyze_c_cpp_file,
            'Scala': self._analyze_scala_file,
            'Elixir': self._analyze_elixir_file,
        }
        for item in self.results["structure"]:
            lang = item["language"]
            fn = dispatch.get(lang)
            if fn:
                fn(self.project_path / item["path"])

    # ── Python ────────────────────────────────────────────────────────
    def _extract_code_snippet(self, source: str, node, max_lines: int = 15) -> str:
        """Extrae un fragmento de código fuente de un nodo AST."""
        try:
            lines = source.splitlines()
            start = node.lineno - 1  # 0-indexed
            end = getattr(node, 'end_lineno', None)
            if end is None:
                end = min(start + max_lines, len(lines))
            else:
                end = min(end, start + max_lines)
            snippet_lines = lines[start:end]
            if end < getattr(node, 'end_lineno', end):
                snippet_lines.append('    # ... (código continúa)')
            return '\n'.join(snippet_lines)
        except Exception:
            return ""

    @staticmethod
    def _generate_endpoint_description(method: str, path: str, handler: str = "", docstring: str = "", lang: str = "es") -> str:
        """Genera una descripción clara y contextual para un endpoint HTTP."""
        if docstring and docstring.strip():
            first_line = docstring.strip().split('\n---')[0].split('\n\n')[0].strip()
            clean = re.sub(r'^(tags|parameters|responses|summary):.*$', '', first_line, flags=re.MULTILINE | re.IGNORECASE).strip()
            if clean:
                return clean

        m = (method or 'GET').upper()
        p = path or '/'
        p_lower = p.lower()
        h_lower = (handler or '').lower()
        is_en = str(lang).lower().startswith('en')

        if any(k in p_lower or k in h_lower for k in ['login', 'signin', 'auth']):
            return "User authentication endpoint: validates credentials and returns session token." if is_en else "Endpoint de autenticación: verifica credenciales de acceso y emite token de sesión."
        if any(k in p_lower or k in h_lower for k in ['logout', 'signout']):
            return "Session termination endpoint: invalidates current user authentication." if is_en else "Endpoint de cierre de sesión: invalida la autenticación actual del usuario."
        if any(k in p_lower or k in h_lower for k in ['register', 'signup']):
            return "User registration endpoint: creates new user accounts in the platform." if is_en else "Endpoint de registro: procesa la creación de nuevas cuentas de usuario."
        if any(k in p_lower or k in h_lower for k in ['profile', 'me']):
            if m == 'GET':
                return "Profile retrieval endpoint: returns authenticated user profile details." if is_en else "Endpoint de perfil: consulta la información y detalles del usuario autenticado."
            return "Profile update endpoint: modifies authenticated user account details." if is_en else "Endpoint de actualización de perfil: modifica datos de la cuenta del usuario."
        if any(k in p_lower or k in h_lower for k in ['export', 'download', 'pdf', 'csv', 'report']):
            return f"Export endpoint: generates downloadable documents or data for {p}." if is_en else f"Endpoint de exportación: genera y descarga reportes o documentos para {p}."

        segments = [s for s in p.strip('/').split('/') if s and not s.startswith(('<', '{', ':', '['))]
        resource = segments[-1].replace('_', ' ').replace('-', ' ') if segments else 'recurso'
        resource_en = segments[-1].replace('_', ' ').replace('-', ' ') if segments else 'resource'
        has_id = any(s.startswith(('<', '{', ':', '[')) for s in p.strip('/').split('/'))

        if m == 'GET':
            if has_id:
                return f"Retrieves details of a specific {resource_en} by identifier." if is_en else f"Obtiene los detalles del recurso {resource} especificado por su identificador."
            return f"Retrieves the list or collection of {resource_en} resources." if is_en else f"Consulta y devuelve la lista de elementos de {resource}."
        elif m == 'POST':
            return f"Creates or registers a new {resource_en} resource." if is_en else f"Crea o registra un nuevo recurso de tipo {resource}."
        elif m == 'PUT':
            return f"Updates or completely replaces the specified {resource_en} resource." if is_en else f"Actualiza o reemplaza completamente el recurso {resource} especificado."
        elif m == 'PATCH':
            return f"Partially updates specific attributes of the {resource_en} resource." if is_en else f"Aplica cambios parciales a los atributos del recurso {resource}."
        elif m == 'DELETE':
            return f"Deletes or permanently removes the specified {resource_en} resource." if is_en else f"Elimina de forma permanente el recurso {resource} especificado."
        elif m == 'OPTIONS':
            return f"Inspects permitted HTTP communication options for {p}." if is_en else f"Consulta las opciones HTTP permitidas para la ruta {p}."
        elif m == 'HEAD':
            return f"Retrieves HTTP response headers without body for {p}." if is_en else f"Obtiene las cabeceras HTTP de respuesta sin cuerpo para {p}."

        return f"Endpoint {m} {p}"

    @staticmethod
    def _generate_class_description(name: str, bases: list, methods: list, fields: list = None, docstring: str = "", is_model: bool = False, lang: str = "es") -> str:
        """Genera una descripción contextual para una clase del proyecto."""
        if docstring and docstring.strip():
            clean = docstring.strip().split('\n\n')[0].strip()
            if clean:
                return clean
        is_en = str(lang).lower().startswith('en')
        n_lower = name.lower()
        if is_model:
            f_count = len(fields) if fields else 0
            if is_en:
                return f"Data model representing the {name} domain entity with {f_count} persistent field(s)."
            return f"Modelo de datos que representa la entidad {name} con {f_count} campo(s) persistente(s) en la base de datos."
        if any(k in n_lower for k in ['controller', 'view', 'handler']):
            if is_en:
                return f"Controller class managing incoming requests and orchestration for {name}."
            return f"Clase controladora encargada de gestionar peticiones y orquestar respuestas para {name}."
        if any(k in n_lower for k in ['service', 'manager']):
            if is_en:
                return f"Service layer class encapsulating business logic and workflows for {name}."
            return f"Capa de servicio que encapsula la lógica de negocio y flujos de trabajo de {name}."
        if any(k in n_lower for k in ['repository', 'dao']):
            if is_en:
                return f"Data access class handling database queries and storage for {name}."
            return f"Clase de acceso a datos que gestiona consultas y persistencia para {name}."

        m_count = len(methods) if methods else 0
        if is_en:
            return f"Class {name} defining state and behavior with {m_count} method(s)."
        return f"Clase {name} que encapsula estructura de datos y comportamiento con {m_count} método(s)."

    @staticmethod
    def _generate_model_description(name: str, bases: list, fields: list, methods: list, docstring: str = "", lang: str = "es") -> str:
        """Genera una descripción técnica para un modelo de datos o entidad."""
        if docstring and docstring.strip():
            clean = docstring.strip().split('\n\n')[0].strip()
            if clean:
                return clean
        is_en = str(lang).lower().startswith('en')
        field_names = [f.get('name') for f in (fields or []) if isinstance(f, dict) and f.get('name')]
        f_summary = f" ({', '.join(field_names[:4])})" if field_names else ""
        if is_en:
            return f"Domain data model representing the {name} entity{f_summary}, handling persistent data schema and business rules."
        return f"Modelo de datos de dominio que define la entidad {name}{f_summary}, gestionando la estructura de persistencia y reglas de negocio asociadas."

    def _parse_python_route_decorator(self, dec, filepath: str, handler: str, docstring: str, lineno: int):
        """Analiza un decorador AST de ruta en Python y devuelve los endpoints detectados."""
        try:
            if not isinstance(dec, ast.Call):
                return None

            func_attr = ""
            if isinstance(dec.func, ast.Attribute):
                func_attr = dec.func.attr.lower()
            elif isinstance(dec.func, ast.Name):
                func_attr = dec.func.id.lower()

            methods = []
            path = "/"
            framework = "Flask"
            http_verbs = {'get', 'post', 'put', 'delete', 'patch', 'options', 'head'}

            if func_attr in http_verbs:
                methods = [func_attr.upper()]
                framework = "Flask/FastAPI"
                if dec.args:
                    if isinstance(dec.args[0], ast.Constant):
                        path = str(dec.args[0].value)
                    elif hasattr(ast, 'Str') and isinstance(dec.args[0], ast.Str):
                        path = str(dec.args[0].s)
            elif func_attr == 'route':
                framework = "Flask"
                if dec.args:
                    if isinstance(dec.args[0], ast.Constant):
                        path = str(dec.args[0].value)
                    elif hasattr(ast, 'Str') and isinstance(dec.args[0], ast.Str):
                        path = str(dec.args[0].s)

                for kw in dec.keywords:
                    if kw.arg in ('rule', 'path') and isinstance(kw.value, ast.Constant):
                        path = str(kw.value.value)
                    elif kw.arg == 'methods':
                        if isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                            for elt in kw.value.elts:
                                if isinstance(elt, ast.Constant):
                                    methods.append(str(elt.value).upper())
                                elif hasattr(ast, 'Str') and isinstance(elt, ast.Str):
                                    methods.append(str(elt.s).upper())

                if not methods:
                    methods = ['GET']

            if not methods:
                return None

            clean_doc = docstring.strip().split('\n---')[0].split('\n\n')[0].strip() if docstring else ""
            endpoints = []
            for m in methods:
                desc = self._generate_endpoint_description(m, path, handler, clean_doc)
                endpoints.append({
                    "method": m,
                    "path": path,
                    "file": filepath,
                    "framework": framework,
                    "handler": handler,
                    "line": lineno,
                    "docstring": clean_doc,
                    "description": desc,
                })
            return endpoints
        except Exception:
            return None

    def _analyze_python_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(source)
            rel = str(filepath.relative_to(self.project_path))
            detected_endpoints = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn_doc = ast.get_docstring(node) or ""
                    self.results["functions"].append({
                        "name": node.name, "file": rel, "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno),
                        "params": [a.arg for a in node.args.args],
                        "docstring": fn_doc,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "complexity": self._estimate_complexity(node),
                        "code_snippet": self._extract_code_snippet(source, node),
                    })

                    # Detect endpoints directly on function decorators
                    for dec in node.decorator_list:
                        eps = self._parse_python_route_decorator(dec, rel, node.name, fn_doc, node.lineno)
                        if eps:
                            for ep in eps:
                                self.results["endpoints"].append(ep)
                                detected_endpoints.append((ep["method"], ep["path"]))

                elif isinstance(node, ast.ClassDef):
                    bases = []
                    for b in node.bases:
                        try:
                            bases.append(ast.unparse(b) if hasattr(ast, 'unparse') else str(b))
                        except Exception:
                            pass

                    # Extract class fields / column attributes
                    fields = []
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    field_type = ""
                                    if isinstance(item.value, ast.Call):
                                        try:
                                            field_type = ast.unparse(item.value.func) if hasattr(ast, 'unparse') else ""
                                        except Exception:
                                            field_type = "Call"
                                    elif isinstance(item.value, ast.Constant):
                                        field_type = type(item.value.value).__name__
                                    fields.append({"name": target.id, "type": field_type or "Attribute"})
                        elif isinstance(item, ast.AnnAssign):
                            if isinstance(item.target, ast.Name):
                                try:
                                    field_type = ast.unparse(item.annotation) if hasattr(ast, 'unparse') else "Any"
                                except Exception:
                                    field_type = "Any"
                                fields.append({"name": item.target.id, "type": field_type})

                    cls_methods = [n.name for n in ast.walk(node)
                                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    cls_doc = ast.get_docstring(node) or ""

                    # Detect whether this class represents a Data Model
                    is_model = (
                        any(kw in node.name.lower() for kw in ["model", "schema", "entity", "dto", "dao", "table"])
                        or any(kw in rel.lower() for kw in ["model", "schema", "entity", "dto", "dao"])
                        or any(any(m_kw in b.lower() for m_kw in ["model", "base", "document", "sqlmodel", "entity"]) for b in bases)
                        or any("column" in f.get("type", "").lower() or "field" in f.get("type", "").lower() for f in fields)
                    )

                    cls_desc = self._generate_class_description(node.name, bases, cls_methods, fields, cls_doc, is_model)

                    class_data = {
                        "name": node.name, "file": rel, "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno),
                        "methods": cls_methods,
                        "bases": bases,
                        "fields": fields,
                        "is_model": is_model,
                        "docstring": cls_doc,
                        "description": cls_desc,
                        "code_snippet": self._extract_code_snippet(source, node),
                    }
                    self.results["classes"].append(class_data)

                    if is_model:
                        model_desc = self._generate_model_description(node.name, bases, fields, cls_methods, cls_doc)
                        model_data = dict(class_data)
                        model_data["description"] = model_desc
                        self.results["models"].append(model_data)

            # Fallback regex search for routes not detected via AST
            self._detect_python_endpoints(source, rel, exclude=detected_endpoints)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    def _detect_python_endpoints(self, source, filepath, exclude=None):
        """
        Detecta endpoints en archivos Python usando patrones habituales de frameworks.
        Soporta Flask/FastAPI, rutas con methods= y decoradores de Django.
        """
        exclude_set = set(exclude or [])
        # Pattern 1: @app.get('/path'), @router.post('/path')
        p1 = r'@(?:\w+)\.(get|post|put|delete|patch|options|head)\(\s*["\']([^"\']+)["\']'
        for m in re.finditer(p1, source, re.IGNORECASE):
            method = m.group(1).upper()
            path = m.group(2)
            if (method, path) not in exclude_set:
                exclude_set.add((method, path))
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({
                    "method": method, "path": path, "file": filepath,
                    "framework": "Flask/FastAPI", "description": desc
                })

        # Pattern 2: @app.route('/path', methods=['GET', 'POST'])
        p2 = r'@(?:\w+)\.route\(\s*["\']([^"\']+)["\'](?:[^)]*?methods\s*=\s*\[([^\]]+)\])?'
        for m in re.finditer(p2, source, re.IGNORECASE | re.DOTALL):
            path = m.group(1)
            methods_raw = m.group(2)
            if methods_raw:
                methods = [meth.strip().strip("'\"").upper() for meth in re.findall(r'["\'](\w+)["\']', methods_raw)]
            else:
                methods = ['GET']
            for method in methods:
                if (method, path) not in exclude_set:
                    exclude_set.add((method, path))
                    desc = self._generate_endpoint_description(method, path)
                    self.results["endpoints"].append({
                        "method": method, "path": path, "file": filepath,
                        "framework": "Flask", "description": desc
                    })

        # Pattern 3: Django path('path/', view)
        p3 = r'path\(\s*["\']([^"\']*)["\']'
        for m in re.finditer(p3, source):
            path = m.group(1)
            method = 'GET'
            if (method, path) not in exclude_set:
                exclude_set.add((method, path))
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({
                    "method": method, "path": path, "file": filepath,
                    "framework": "Django", "description": desc
                })

    # ── JS / TS ───────────────────────────────────────────────────────
    def _analyze_js_ts_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            # Routes
            for m in re.finditer(r'(?:app|router)\.(get|post|put|delete|patch|options)\(\s*["`\']([^"`\']+)["`\']', source, re.I):
                method = m.group(1).upper()
                path = m.group(2)
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "Express.js", "description": desc})
            for m in re.finditer(r'@(Get|Post|Put|Delete|Patch)\(\s*["`\']?([^"`\'\)]*)["`\']?\)', source):
                method = m.group(1).upper()
                path = m.group(2) or '/'
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "NestJS", "description": desc})
            # Functions
            for pattern in [
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
                r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)',
            ]:
                for m in re.finditer(pattern, source):
                    name, params_str = m.groups()
                    if name and len(name) > 1:
                        params = [p.strip().split(':')[0].strip() for p in params_str.split(',') if p.strip()]
                        self.results["functions"].append({"name": name, "file": rel, "params": params, "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            # Classes & Models
            for m in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                name = m.group(1)
                base = m.group(2) or ""
                bases = [base] if base else []
                is_model = (
                    any(kw in name.lower() for kw in ["model", "schema", "entity", "dto", "dao"])
                    or any(kw in rel.lower() for kw in ["model", "schema", "entity", "dto", "dao"])
                    or any(kw in base.lower() for kw in ["model", "schema", "entity"])
                )
                desc = self._generate_class_description(name, bases, [], is_model=is_model)
                class_info = {"name": name, "file": rel, "line": 0, "methods": [], "bases": bases, "docstring": "", "description": desc, "is_model": is_model}
                self.results["classes"].append(class_info)
                if is_model:
                    m_desc = self._generate_model_description(name, bases, [], [], "")
                    m_info = dict(class_info)
                    m_info["description"] = m_desc
                    self.results["models"].append(m_info)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Java ──────────────────────────────────────────────────────────
    def _analyze_java_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            method_map = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE', 'PatchMapping': 'PATCH', 'RequestMapping': 'GET'}
            for m in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\(?["\']?([^"\')\n]*)["\']?\)?', source):
                method = method_map.get(m.group(1), 'GET')
                path = m.group(2).strip() or '/'
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "Spring", "description": desc})
            for m in re.finditer(r'(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                if name not in ('if', 'for', 'while', 'switch', 'return', 'class'):
                    self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:public\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                name = m.group(1)
                bases = [m.group(2)] if m.group(2) else []
                is_model = any(kw in name.lower() for kw in ["model", "entity", "dto"]) or "model" in rel.lower() or "@Entity" in source
                desc = self._generate_class_description(name, bases, [], is_model=is_model)
                class_info = {"name": name, "file": rel, "line": 0, "methods": [], "bases": bases, "docstring": "", "description": desc, "is_model": is_model}
                self.results["classes"].append(class_info)
                if is_model:
                    m_desc = self._generate_model_description(name, bases, [], [], "")
                    m_info = dict(class_info)
                    m_info["description"] = m_desc
                    self.results["models"].append(m_info)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── PHP ───────────────────────────────────────────────────────────
    def _analyze_php_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'Route::(get|post|put|delete|patch|any)\s*\(\s*["\']([^"\']+)["\']', source, re.I):
                method = m.group(1).upper()
                path = m.group(2)
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "Laravel", "description": desc})
            for m in re.finditer(r'(?:public\s+|private\s+|protected\s+)?(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().lstrip('$') for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
                name = m.group(1)
                bases = [m.group(2)] if m.group(2) else []
                is_model = any(kw in name.lower() for kw in ["model", "entity", "dto"]) or "model" in rel.lower() or any("model" in b.lower() for b in bases)
                desc = self._generate_class_description(name, bases, [], is_model=is_model)
                class_info = {"name": name, "file": rel, "line": 0, "methods": [], "bases": bases, "docstring": "", "description": desc, "is_model": is_model}
                self.results["classes"].append(class_info)
                if is_model:
                    m_desc = self._generate_model_description(name, bases, [], [], "")
                    m_info = dict(class_info)
                    m_info["description"] = m_desc
                    self.results["models"].append(m_info)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Ruby ──────────────────────────────────────────────────────────
    def _analyze_ruby_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(get|post|put|delete|patch)\s+["\']([^"\']+)["\']', source, re.I):
                method = m.group(1).upper()
                path = m.group(2)
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "Rails/Sinatra", "description": desc})
            for m in re.finditer(r'def\s+(\w+)(?:\(([^)]*)\))?', source):
                name, ps = m.group(1), m.group(2) or ''
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*<\s*(\w+))?', source):
                name = m.group(1)
                bases = [m.group(2)] if m.group(2) else []
                is_model = any(kw in name.lower() for kw in ["model", "entity", "dto"]) or "model" in rel.lower() or any("record" in b.lower() for b in bases)
                desc = self._generate_class_description(name, bases, [], is_model=is_model)
                class_info = {"name": name, "file": rel, "line": 0, "methods": [], "bases": bases, "docstring": "", "description": desc, "is_model": is_model}
                self.results["classes"].append(class_info)
                if is_model:
                    m_desc = self._generate_model_description(name, bases, [], [], "")
                    m_info = dict(class_info)
                    m_info["description"] = m_desc
                    self.results["models"].append(m_info)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Go ────────────────────────────────────────────────────────────
    def _analyze_go_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:r|router|e|app|mux)\.(GET|POST|PUT|DELETE|PATCH|HandleFunc|Handle)\(\s*["`]([^"`]+)["`]', source, re.I):
                method = m.group(1).upper().replace('HANDLEFUNC', 'GET').replace('HANDLE', 'GET')
                path = m.group(2)
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "Go HTTP (Gin/Echo/Fiber)", "description": desc})
            for m in re.finditer(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'type\s+(\w+)\s+struct\s*\{', source):
                name = m.group(1)
                is_model = any(kw in name.lower() for kw in ["model", "entity", "dto"]) or "model" in rel.lower()
                desc = self._generate_class_description(name, [], [], is_model=is_model)
                class_info = {"name": name, "file": rel, "line": 0, "methods": [], "bases": [], "docstring": "", "description": desc, "is_model": is_model}
                self.results["classes"].append(class_info)
                if is_model:
                    m_desc = self._generate_model_description(name, [], [], [], "")
                    m_info = dict(class_info)
                    m_info["description"] = m_desc
                    self.results["models"].append(m_info)
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── C# ────────────────────────────────────────────────────────────
    def _analyze_csharp_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            mm = {'HttpGet': 'GET', 'HttpPost': 'POST', 'HttpPut': 'PUT', 'HttpDelete': 'DELETE', 'HttpPatch': 'PATCH', 'Route': 'GET'}
            for m in re.finditer(r'\[(HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch|Route)(?:\(["\']([^"\']*)["\'])?\]', source):
                method = mm.get(m.group(1), 'GET')
                path = m.group(2) or '/'
                desc = self._generate_endpoint_description(method, path)
                self.results["endpoints"].append({"method": method, "path": path, "file": rel, "framework": "ASP.NET Core", "description": desc})
            for m in re.finditer(r'(?:public|private|protected|internal)\s+(?:async\s+)?(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1] for p in ps.split(',') if p.strip()], "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            for m in re.finditer(r'(?:public\s+)?class\s+(\w+)(?:\s*:\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Kotlin ────────────────────────────────────────────────────────
    def _analyze_kotlin_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            mm = {'GetMapping': 'GET', 'PostMapping': 'POST', 'PutMapping': 'PUT', 'DeleteMapping': 'DELETE', 'PatchMapping': 'PATCH'}
            for m in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\(?["\']?([^"\')\n]*)["\']?\)?', source):
                self.results["endpoints"].append({"method": mm.get(m.group(1), 'GET'), "path": m.group(2).strip() or '/', "file": rel, "framework": "Spring/Ktor"})
            for m in re.finditer(r'fun\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:data\s+)?class\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Rust ──────────────────────────────────────────────────────────
    def _analyze_rust_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'#\[(?:get|post|put|delete|patch)\("[^"]*"\)\]', source):
                method = re.search(r'#\[(\w+)', m.group(0))
                path_ = re.search(r'"([^"]+)"', m.group(0))
                if method and path_:
                    self.results["endpoints"].append({"method": method.group(1).upper(), "path": path_.group(1), "file": rel, "framework": "Actix/Axum"})
            for m in re.finditer(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*)?\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": 'async' in m.group(0), "complexity": 1})
            for m in re.finditer(r'(?:pub\s+)?struct\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Swift ─────────────────────────────────────────────────────────
    def _analyze_swift_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:func)\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*:\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── C / C++ ───────────────────────────────────────────────────────
    def _analyze_c_cpp_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(?:[\w*]+\s+)+(\w+)\s*\(([^)]*)\)\s*(?:const\s*)?\{', source):
                name, ps = m.groups()
                if name not in ('if', 'for', 'while', 'switch', 'return', 'do'):
                    self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split()[-1].lstrip('*') for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'class\s+(\w+)(?:\s*:\s*(?:public|private|protected)?\s*(\w+))?', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [m.group(2)] if m.group(2) else [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Scala ─────────────────────────────────────────────────────────
    def _analyze_scala_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'def\s+(\w+)\s*(?:\(([^)]*)\))?', source):
                name, ps = m.group(1), m.group(2) or ''
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip().split(':')[0].strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'(?:class|object|trait|case class)\s+(\w+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Elixir ────────────────────────────────────────────────────────
    def _analyze_elixir_file(self, filepath: Path):
        try:
            source = filepath.read_text(encoding='utf-8', errors='ignore')
            rel = str(filepath.relative_to(self.project_path))
            for m in re.finditer(r'(get|post|put|delete|patch)\s+"([^"]+)"', source, re.I):
                self.results["endpoints"].append({"method": m.group(1).upper(), "path": m.group(2), "file": rel, "framework": "Phoenix"})
            for m in re.finditer(r'def\s+(\w+)\s*\(([^)]*)\)', source):
                name, ps = m.groups()
                self.results["functions"].append({"name": name, "file": rel, "params": [p.strip() for p in ps.split(',') if p.strip()], "docstring": "", "is_async": False, "complexity": 1})
            for m in re.finditer(r'defmodule\s+([\w.]+)', source):
                self.results["classes"].append({"name": m.group(1), "file": rel, "line": 0, "methods": [], "bases": [], "docstring": ""})
        except Exception as e:
            self.results["issues"].append({"file": str(filepath), "error": str(e)})

    # ── Helpers ───────────────────────────────────────────────────────
    def _estimate_complexity(self, node) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                   ast.With, ast.Assert, ast.comprehension,
                                   ast.BoolOp, ast.Try)):
                complexity += 1
        return complexity

    def _calculate_quality_score(self):
        """
        Calcula una puntuación global del proyecto.

        Se penaliza por falta de documentación, complejidad alta y errores
        detectados durante el análisis. Se premia la presencia de tests.
        """
        score = 100
        funcs = self.results["functions"]
        if funcs:
            documented = sum(1 for f in funcs if f.get("docstring"))
            score -= (1 - documented / len(funcs)) * 30
        high_cx = sum(1 for f in funcs if f.get("complexity", 1) > 10)
        score -= min(high_cx * 5, 20)
        issues = len(self.results.get("issues", []))
        score -= min(issues * 2, 20)
        test_fns = sum(1 for f in funcs if 'test' in f['name'].lower())
        if test_fns:
            score = min(100, score + min(test_fns, 10))
        self.results["quality_score"] = max(0, int(score))
        self.results["complexity"] = {
            "avg": round(sum(f.get("complexity", 1) for f in funcs) / max(len(funcs), 1), 2),
            "max": max((f.get("complexity", 1) for f in funcs), default=0),
            "high_complexity_funcs": high_cx,
        }