from datetime import datetime
from services.ai_enhancer import AIEnhancer
import subprocess
import os
import shutil
import zlib
import base64
import mimetypes
import urllib.request
import urllib.error
from pathlib import Path

class DocGenerator:
    """
    Genera documentación técnica profesional completa:
    1. Arquitectura y Diseño
    2. Documentación de Código
    3. API Reference
    4. Guía de Despliegue
    5. Modelos de Datos
    """

    def __init__(self, analysis_results: dict):
        self.r = analysis_results
        self.now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        self.ai_enhancer = AIEnhancer()
        
        # Mejorar documentación con IA si está disponible
        if self.ai_enhancer.is_available():
            self.r = self.ai_enhancer.enhance_documentation(self.r)

    def _render_markdown_table(self, headers: list[str], rows: list[list[str]]) -> str:
        header_line = '| ' + ' | '.join(headers) + ' |'
        separator_line = '| ' + ' | '.join('---' for _ in headers) + ' |'
        row_lines = '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows)
        return f"{header_line}\n{separator_line}\n{row_lines}\n"

    def _graphviz_available(self) -> bool:
        return bool(shutil.which('dot'))

    def _get_plantuml_command(self, temp_file: Path, output_dir: Path):
        if not self._graphviz_available():
            return []

        jar_path = os.environ.get('PLANTUML_JAR_PATH')
        if jar_path and Path(jar_path).exists():
            return ['java', '-jar', str(Path(jar_path)), '-tpng', str(temp_file), '-o', str(output_dir)]

        # Buscar JAR en rutas comunes
        candidates = [
            Path.cwd() / 'plantuml.jar',
            Path.cwd().parent / 'plantuml.jar',
            Path(__file__).resolve().parents[1] / 'plantuml.jar',
            Path('/usr/local/bin/plantuml.jar'),
            Path('C:/plantuml/plantuml.jar'),
            Path('C:/Program Files/PlantUML/plantuml.jar'),
        ]
        for candidate in candidates:
            if candidate.exists():
                return ['java', '-jar', str(candidate), '-tpng', str(temp_file), '-o', str(output_dir)]

        plantuml_bin = shutil.which('plantuml')
        if plantuml_bin:
            return [plantuml_bin, '-tpng', str(temp_file), '-o', str(output_dir)]

        return []

    def _encode6(self, v: int) -> str:
        alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'
        return alphabet[v & 0x3F]

    def _plantuml_encode(self, text: str) -> str:
        compressed = zlib.compress(text.encode('utf-8'))
        compressed = compressed[2:-4]
        res = ''
        i = 0
        while i < len(compressed):
            if i + 2 < len(compressed):
                b1, b2, b3 = compressed[i], compressed[i+1], compressed[i+2]
                res += self._encode6(b1 >> 2)
                res += self._encode6(((b1 & 0x3) << 4) | (b2 >> 4))
                res += self._encode6(((b2 & 0xF) << 2) | (b3 >> 6))
                res += self._encode6(b3 & 0x3F)
                i += 3
            elif i + 1 < len(compressed):
                b1, b2 = compressed[i], compressed[i+1]
                res += self._encode6(b1 >> 2)
                res += self._encode6(((b1 & 0x3) << 4) | (b2 >> 4))
                res += self._encode6((b2 & 0xF) << 2)
                i += 2
            else:
                b1 = compressed[i]
                res += self._encode6(b1 >> 2)
                res += self._encode6((b1 & 0x3) << 4)
                i += 1
        return res

    def _fetch_plantuml_image(self, plantuml_code: str, output_file: Path) -> Path | None:
        default_servers = [
            'https://www.plantuml.com/plantuml',
        ]
        server_url = os.environ.get('PLANTUML_SERVER_URL')
        servers = [server_url] + default_servers if server_url else default_servers
        encoded = self._plantuml_encode(plantuml_code)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'image/png,*/*;q=0.8',
        }
        for server in filter(None, servers):
            for path_variant in ['png', 'svg']:
                ext = 'png' if path_variant == 'png' else 'svg'
                target_url = f"{server.rstrip('/')}/{path_variant}/{encoded}"
                output_path = output_file.with_suffix(f'.{ext}')
                try:
                    request = urllib.request.Request(target_url, headers=headers)
                    with urllib.request.urlopen(request, timeout=20) as response:
                        if response.status != 200:
                            print(f"[PlantUML Error] remote server returned {response.status} for {target_url}")
                            continue
                        content = response.read()
                        content_type = response.headers.get('Content-Type', '')
                        if ext == 'png':
                            if not content.startswith(b'\x89PNG\r\n\x1a\n'):
                                print(f"[PlantUML Error] remote server returned invalid PNG for {target_url}")
                                continue
                        elif ext == 'svg':
                            text = content.decode('utf-8', errors='ignore').strip()
                            if not (text.startswith('<svg') or text.startswith('<?xml')):
                                print(f"[PlantUML Error] remote server returned invalid SVG for {target_url}")
                                continue
                        output_path.write_bytes(content)
                        if self._is_valid_image(output_path):
                            return output_path
                        output_path.unlink(missing_ok=True)
                except urllib.error.HTTPError as e:
                    print(f"[PlantUML Error] remote fetch failed {e.code} for {target_url}: {e.reason}")
                except urllib.error.URLError as e:
                    print(f"[PlantUML Error] remote fetch failed for {target_url}: {e}")
                except Exception as e:
                    print(f"[PlantUML Error] remote fetch failed for {target_url}: {e}")
        return None

    def _image_to_data_uri(self, image_path: Path) -> str:
        try:
            if not self._is_valid_image(image_path):
                return ""
            data = image_path.read_bytes()
            mime_type = mimetypes.guess_type(str(image_path))[0] or 'application/octet-stream'
            encoded = base64.b64encode(data).decode('ascii')
            return f'data:{mime_type};base64,{encoded}'
        except Exception as e:
            print(f"[PlantUML Error] failed to encode image to data URI: {e}")
            return ""

    def _is_valid_image(self, image_path: Path) -> bool:
        try:
            data = image_path.read_bytes()
            suffix = image_path.suffix.lower()
            if suffix == '.png':
                if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) <= 200:
                    return False
            elif suffix == '.svg':
                text = data.decode('utf-8', errors='ignore').strip()
                if not (text.startswith('<svg') or text.startswith('<?xml')):
                    return False
            if self._contains_plantuml_error_text(data):
                print(f"[PlantUML Error] detected PlantUML error image content in {image_path}")
                return False
            return True
        except Exception as e:
            print(f"[PlantUML Error] image validation failed: {e}")
            return False

    def _contains_plantuml_error_text(self, data: bytes) -> bool:
        lower = data.lower()
        error_markers = [
            b'dot executable',
            b'cannot find graphviz',
            b'graphviz not found',
            b'failed to load graphviz',
            b'error while running dot',
            b'you should try',
            b'plantuml error',
            b'cannot find graphviz',
        ]
        return any(marker in lower for marker in error_markers)

    def _generate_plantuml_diagram(self, plantuml_code: str, output_dir: str = "./exports") -> str:
        """Genera un diagrama PlantUML y devuelve una URI de imagen o ruta de archivo."""
        try:
            output_dir_path = Path(output_dir).resolve()
            output_dir_path.mkdir(parents=True, exist_ok=True)
            
            temp_name = f"temp_{os.getpid()}"
            temp_file = output_dir_path / f"{temp_name}.puml"
            temp_file.write_text(plantuml_code, encoding='utf-8')
            
            cmd = self._get_plantuml_command(temp_file, output_dir_path)
            if cmd:
                result = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True
                )
                stderr = (result.stderr or '').lower()
                stdout = (result.stdout or '').lower()
                plantuml_failures = [
                    'cannot find graphviz',
                    'dot executable',
                    'graphviz not found',
                    'failed to load graphviz',
                    'error while running dot',
                    'dot executable does not exist',
                ]
                has_dot_error = any(keyword in stderr for keyword in plantuml_failures) or any(keyword in stdout for keyword in plantuml_failures)
                if result.returncode == 0 and not has_dot_error:
                    temp_file.unlink(missing_ok=True)
                    output_path = output_dir_path / f"{temp_name}.png"
                    if output_path.exists() and self._is_valid_image(output_path):
                        return self._image_to_data_uri(output_path)
                    for f in output_dir_path.glob(f"{temp_name}*.png"):
                        if self._is_valid_image(f):
                            return self._image_to_data_uri(f)
                else:
                    print(f"[PlantUML Error] local command failed: returncode={result.returncode}")
                    if stderr:
                        print(stderr)
                    if stdout:
                        print(stdout)
                    for f in output_dir_path.glob(f"{temp_name}*.png"):
                        f.unlink(missing_ok=True)

            # Fallback remoto si no hay Jar o el comando falló
            remote_image = self._fetch_plantuml_image(plantuml_code, output_dir_path / f"{temp_name}_remote")
            if remote_image:
                temp_file.unlink(missing_ok=True)
                return self._image_to_data_uri(remote_image)

            temp_file.unlink(missing_ok=True)
            return ""
        except Exception as e:
            print(f"[PlantUML Error] {e}")
            return ""

    def generate(self) -> dict:
        return {
            "generated_at": self.now,
            "readme":         self._readme(),
            "architecture":   self._architecture(),
            "api_docs":       self._api_docs(),
            "class_docs":     self._class_docs(),
            "function_docs":  self._function_docs(),
            "data_models":    self._data_models(),
            "deployment":     self._deployment(),
            "quality_report": self._quality_report(),
            "full_markdown":  self._full_markdown(),
        }

    # ─── 1. README ────────────────────────────────────────────────────────────
    def _readme(self) -> str:
        lang   = self.r.get("primary_language", "Desconocido")
        langs  = self.r.get("languages", {})
        fns    = self.r.get("functions", [])
        cls    = self.r.get("classes", [])
        eps    = self.r.get("endpoints", [])
        files  = self.r.get("total_files", 0)
        score  = self.r.get("quality_score", 0)

        lang_rows = [[l, f"{c} archivos"] for l, c in langs.items()]
        metrics_rows = [
            ["Total de archivos", str(files)],
            ["Funciones", str(len(fns))],
            ["Clases", str(len(cls))],
            ["Endpoints API", str(len(eps))],
            ["Score de calidad", f"{score}/100"],
            ["Funciones documentadas", f"{sum(1 for f in fns if f.get('docstring'))} / {len(fns)}"],
            ["Clases documentadas", f"{sum(1 for c in cls if c.get('docstring'))} / {len(cls)}"],
        ]

        return f"""# Documentación del Proyecto

> Generado automáticamente por **AutoDocs AI** — {self.now}

## Resumen Ejecutivo

Este proyecto está desarrollado principalmente en **{lang}** y cuenta con
{files} archivos fuente, {len(fns)} funciones, {len(cls)} clases y
{len(eps)} endpoints de API documentados. El score de calidad del código es
**{score}/100**.

## Stack Tecnológico

{self._render_markdown_table(['Lenguaje', 'Cantidad'], lang_rows)}

## Estadísticas del Proyecto

{self._render_markdown_table(['Métrica', 'Valor'], metrics_rows)}
"""

    # ─── 2. ARQUITECTURA ──────────────────────────────────────────────────────
    def _architecture(self) -> str:
        struct  = self.r.get("structure", [])
        langs   = self.r.get("languages", {})
        eps     = self.r.get("endpoints", [])
        cls     = self.r.get("classes", [])
        
        # Agregar insights de IA si están disponibles
        ai_insights = self.r.get("ai_architecture_insights", "")

        # Agrupar por directorio raíz
        dirs = {}
        for item in struct:
            parts = item["path"].replace("\\", "/").split("/")
            top = parts[0] if len(parts) > 1 else "(raíz)"
            dirs.setdefault(top, []).append(item)

        dir_section = ""
        for d, items in list(dirs.items())[:20]:
            exts = {}
            for i in items:
                ext = i["name"].rsplit(".", 1)[-1] if "." in i["name"] else "sin ext"
                exts[ext] = exts.get(ext, 0) + 1
            ext_str = ", ".join(f".{e}({n})" for e, n in exts.items())
            dir_section += f"- **`{d}/`** — {len(items)} archivos [{ext_str}]\n"

        lang_dist = "\n".join(
            f"- {l}: {c} archivos ({round(c/max(sum(langs.values()),1)*100)}%)"
            for l, c in sorted(langs.items(), key=lambda x: -x[1])
        )

        # Diagrama de casos de uso en PlantUML
        use_cases_puml = "@startuml\n"
        use_cases_puml += "actor Usuario as user\n"
        use_cases_puml += "package \"Sistema\" {\n"
        for ep in eps[:10]:
            method = ep.get("method", "GET")
            path = ep.get("path", "/").replace("/", "_").replace("{", "").replace("}", "")
            use_cases_puml += f'  usecase "{method} {ep.get("path", "/")}" as uc_{path}\n'
            use_cases_puml += f'  user --> uc_{path}\n'
        if len(eps) > 10:
            use_cases_puml += '  usecase "Otros endpoints" as uc_other\n'
            use_cases_puml += '  user --> uc_other\n'
        use_cases_puml += "}\n@enduml"
        
        # Generar diagrama de casos de uso
        use_case_diagram = ""
        if eps:
            diagram_path = self._generate_plantuml_diagram(use_cases_puml)
            if diagram_path:
                use_case_diagram = (
                    f"\n\n<div style=\"margin: 1.5rem 0;\">"
                    f"<img src=\"{diagram_path}\" alt=\"Diagrama de Casos de Uso\" "
                    f"style=\"max-width: 100%; height: auto; border: 1px solid #cbd5e1; border-radius: 8px; display:block;\">"
                    f"</div>\n"
                )

        # Diagrama de infraestructura en PlantUML
        infra_puml = """@startuml
skinparam componentStyle rectangle
package "Cliente / Frontend" {
  [Navegador] as browser
  [App Móvil] as mobile
  [CLI] as cli
}
package "API / Backend" {
  [Rutas] as routes
  [Lógica de Negocio] as logic
  routes --> logic
}
database "Base de Datos" as db
database "Caché" as cache
[Servicios Ext.] as ext
logic --> db
logic --> cache
logic --> ext
browser --> routes
mobile --> routes
cli --> routes
@enduml"""
        
        # Generar diagrama de infraestructura
        infra_diagram = ""
        diagram_path = self._generate_plantuml_diagram(infra_puml)
        if diagram_path:
            infra_diagram = (
                f"\n\n<div style=\"margin: 1.5rem 0;\">"
                f"<img src=\"{diagram_path}\" alt=\"Diagrama de Infraestructura\" "
                f"style=\"max-width: 100%; height: auto; border: 1px solid #cbd5e1; border-radius: 8px; display:block;\">"
                f"</div>\n"
            )

        # Diagrama de clases en PlantUML
        class_puml = "@startuml\n"
        for c in cls[:15]:
            class_name = c.get("name", "Unknown")
            class_puml += f'class "{class_name}" {{\n'
            methods = c.get("methods", [])
            for m in methods[:5]:
                class_puml += f'  {m}\n'
            if len(methods) > 5:
                class_puml += f'  ... {len(methods) - 5} más\n'
            class_puml += '}\n'
        class_puml += "@enduml"
        
        # Detectar clases "básicas" (sin métodos ni atributos)
        basic_classes = [c for c in cls if not c.get("methods") and not c.get("attributes")]
        basic_class_warning = ""
        if basic_classes:
            names = ", ".join(f"`{c.get('name', '?')}`" for c in basic_classes[:10])
            extra = f" y {len(basic_classes) - 10} más" if len(basic_classes) > 10 else ""
            basic_class_warning = (
                f"\n\n> ⚠️ **Clases con información incompleta:** Las siguientes clases aparecen sin métodos ni atributos documentados: "
                f"{names}{extra}. "
                f"Para que el diagrama se visualice correctamente, agrega métodos, propiedades o docstrings a estas clases en tu código fuente y regenera la documentación.\n"
            )

        # Generar diagrama de clases
        class_diagram = ""
        if cls:
            diagram_path = self._generate_plantuml_diagram(class_puml)
            if diagram_path:
                class_diagram = (
                    f"\n\n<div style=\"margin: 1.5rem 0;\">"
                    f"<img src=\"{diagram_path}\" alt=\"Diagrama de Clases\" "
                    f"style=\"max-width: 100%; height: auto; border: 1px solid #cbd5e1; border-radius: 8px; display:block;\">"
                    f"</div>\n"
                )
            class_diagram += basic_class_warning

        return f"""## 2. Documentación de Arquitectura y Diseño

### 2.1 Estructura de Directorios

```
proyecto/
{chr(10).join(f'├── {d}/' for d in list(dirs.keys())[:15])}
```

### 2.2 Distribución por Capas

{dir_section}

### 2.3 Distribución de Lenguajes

{lang_dist}

### 2.4 Diagrama de Infraestructura

{infra_diagram}

### 2.5 Diagrama de Casos de Uso

{use_case_diagram}

### 2.6 Diagrama de Clases

{class_diagram}

### 2.7 Patrones Detectados

{self._detect_patterns()}

### 2.8 Insights de Arquitectura (IA)

{ai_insights if ai_insights else "No se generaron insights de IA - configura GEMINI_API_KEY en el archivo .env para habilitar esta función."}
"""

    def _detect_patterns(self) -> str:
        eps   = self.r.get("endpoints", [])
        cls   = self.r.get("classes", [])
        fns   = self.r.get("functions", [])
        patterns = []

        if eps:
            frameworks = set(e.get("framework", "") for e in eps)
            patterns.append(f"- **API REST**: {len(eps)} endpoints detectados ({', '.join(frameworks)})")
        if any("Model" in c["name"] or "model" in c["name"].lower() for c in cls):
            patterns.append("- **Patrón MVC**: clases Model detectadas")
        if any("test" in f["name"].lower() or "Test" in f["name"] for f in fns):
            tc = sum(1 for f in fns if "test" in f["name"].lower())
            patterns.append(f"- **Testing**: {tc} funciones de prueba detectadas")
        if any("__init__" in f["name"] for f in fns):
            patterns.append("- **Programación Orientada a Objetos**: constructores detectados")
        async_fns = sum(1 for f in fns if f.get("is_async"))
        if async_fns:
            patterns.append(f"- **Programación Asíncrona**: {async_fns} funciones async/await")

        return "\n".join(patterns) if patterns else "- No se detectaron patrones específicos"

    # ─── 3. API DOCS ──────────────────────────────────────────────────────────
    def _api_docs(self) -> list:
        docs = []
        for ep in self.r.get("endpoints", []):
            # Usar descripción de IA si está disponible, sino usar descripción genérica
            description = ep.get("ai_description") or f"Endpoint {ep.get('method')} {ep.get('path')}"
            docs.append({
                "method":      ep.get("method"),
                "path":        ep.get("path"),
                "file":        ep.get("file"),
                "framework":   ep.get("framework"),
                "description": description,
                "parameters":  [],
                "responses": {
                    "200": {"description": "Operación exitosa"},
                    "400": {"description": "Solicitud incorrecta"},
                    "401": {"description": "No autorizado"},
                    "404": {"description": "Recurso no encontrado"},
                    "500": {"description": "Error interno del servidor"},
                }
            })
        return docs

    def _api_section(self) -> str:
        eps = self.r.get("endpoints", [])
        if not eps:
            return "## 3. Documentación Técnica de Código\n\nNo se detectaron endpoints en este proyecto.\n"

        out = "## 3. Documentación Técnica de Código\n\n"

        # 3.1 Guía de configuración del entorno
        lang = self.r.get("primary_language", "Python")
        install_cmd = {
            "Python": "pip install -r requirements.txt",
            "JavaScript": "npm install",
            "TypeScript": "npm install",
        }.get(lang, "# instalar dependencias")

        out += "### 3.1 Guía de Configuración del Entorno de Desarrollo\n\n"
        out += f"""```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd <nombre-del-proyecto>

# 2. Crear entorno virtual (recomendado para Python)
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\\Scripts\\activate     # Windows

# 3. Instalar dependencias
{install_cmd}

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores locales

# 5. Ejecutar en modo desarrollo
python app.py  # o npm run dev
```

"""

        # 3.2 Documentación de API
        out += f"### 3.2 Documentación de API\n\nTotal de endpoints detectados: **{len(eps)}**\n\n"

        by_file = {}
        for ep in eps:
            by_file.setdefault(ep.get("file", "desconocido"), []).append(ep)

        for f, endpoints in by_file.items():
            out += f"#### Módulo: `{f}`\n\n"
            for ep in endpoints:
                method_icons = {"GET": "[GET]", "POST": "[POST]", "PUT": "[PUT]", "DELETE": "[DEL]", "PATCH": "[PATCH]"}
                icon = method_icons.get(ep.get("method", ""), "[GET]")
                out += f"##### {icon} `{ep.get('method')} {ep.get('path')}`\n\n"
                out += f"- **Framework**: {ep.get('framework', 'Desconocido')}\n"
                out += f"- **Archivo**: `{ep.get('file')}`\n\n"
                # Mostrar descripción de IA si está disponible
                ai_desc = ep.get("ai_description")
                if ai_desc:
                    out += f"> {ai_desc}\n\n"
                out += "**Parámetros esperados:**\n\n"
                method = ep.get("method", "GET")
                if method in ("POST", "PUT", "PATCH"):
                    out += "- `body` (JSON, requerido): Cuerpo de la solicitud\n"
                out += "- `Authorization` (Header, requerido): Bearer JWT token\n\n"
                out += "**Códigos de respuesta:**\n\n"
                out += "- `200` — Operación exitosa\n"
                out += "- `400` — Solicitud incorrecta\n"
                out += "- `401` — No autorizado\n"
                out += "- `404` — Recurso no encontrado\n"
                out += "- `500` — Error interno del servidor\n\n"
                out += "---\n\n"

        # 3.3 Comentarios y JSDoc / Docstrings
        fns = self.r.get("functions", [])
        documented = [f for f in fns if f.get("docstring")]
        undocumented = [f for f in fns if not f.get("docstring")]
        doc_pct = round(len(documented) / max(len(fns), 1) * 100)

        out += "### 3.3 Estado de Comentarios y Docstrings\n\n"
        out += f"**Total de funciones:** {len(fns)}\n\n"
        out += f"- **[OK] Documentadas:** {len(documented)} ({doc_pct}%)\n"
        out += f"- **[X] Sin documentar:** {len(undocumented)} ({100 - doc_pct}%)\n\n"
        out += "**Visualización de documentación:**\n\n"
        out += f"```text\n[{'█' * int(doc_pct/5)}{'░' * int((100-doc_pct)/5)}]\n{doc_pct}% documentado\n```\n\n"

        if documented:
            out += "**Ejemplo de docstrings detectados:**\n\n"
            for fn in documented[:3]:
                params_str = ", ".join(fn.get("params", []))
                out += f"```python\ndef {fn['name']}({params_str}):\n    \"\"\"\n    {fn['docstring']}\n    \"\"\"\n    ...\n```\n\n"

        if undocumented:
            out += "**Funciones que requieren documentación:**\n\n"
            for fn in undocumented[:5]:
                params_str = ", ".join(fn.get("params", []))
                out += f"- `{fn['name']}({params_str})` en `{fn.get('file', '?')}`\n"
            if len(undocumented) > 5:
                out += f"- ... y {len(undocumented) - 5} más\n"
            out += "\n"

        # 3.4 Planes de Prueba (Testing)
        test_fns = [f for f in fns if "test" in f["name"].lower() or f["name"].startswith("test_")]
        out += "### 3.4 Planes de Prueba (Testing)\n\n"
        if test_fns:
            out += f"Se detectaron **{len(test_fns)} funciones de prueba**:\n\n"
            rows = [[f"`{fn['name']}`", f"`{fn.get('file', '?')}`"] for fn in test_fns[:10]]
            out += self._render_markdown_table(['Función de Test', 'Archivo'], rows)
        else:
            out += "No se detectaron pruebas automatizadas. Se recomienda implementar:\n\n"
            out += "```python\n# Ejemplo de estructura de tests recomendada\nimport pytest\n\nclass TestEndpoints:\n    def test_get_returns_200(self, client):\n        response = client.get('/api/endpoint')\n        assert response.status_code == 200\n\n    def test_post_creates_resource(self, client):\n        data = {'name': 'test'}\n        response = client.post('/api/endpoint', json=data)\n        assert response.status_code == 201\n\n    def test_unauthorized_returns_401(self, client):\n        response = client.get('/api/protected')\n        assert response.status_code == 401\n```\n\n"
            out += "**Escenarios de prueba recomendados:**\n\n"
            rows = []
            for ep in eps[:6]:
                rows.append([f"{ep.get('method')} {ep.get('path')} — respuesta 200", "Integración", "Alta"])
                rows.append([f"{ep.get('method')} {ep.get('path')} — sin auth (401)", "Seguridad", "Alta"])
            out += self._render_markdown_table(['Escenario', 'Tipo', 'Prioridad'], rows)
            out += "\n"

        return out

    # ─── 4. CLASES ────────────────────────────────────────────────────────────
    def _class_docs(self) -> list:
        docs = []
        for c in self.r.get("classes", []):
            # Usar descripción de IA si está disponible, sino usar docstring
            description = c.get("ai_description") or c.get("docstring") or f"Clase {c['name']}"
            docs.append({
                "name":        c["name"],
                "file":        c["file"],
                "line":        c.get("line"),
                "description": description,
                "inherits":    c.get("bases", []),
                "methods":     c.get("methods", []),
                "method_count": len(c.get("methods", [])),
            })
        return docs

    def _classes_section(self) -> str:
        classes = self.r.get("classes", [])
        if not classes:
            return "## 4. Clases\n\nNo se detectaron clases en este proyecto.\n"

        out = f"## 4. Documentación de Clases\n\nTotal: **{len(classes)} clases**\n\n"
        for c in classes:
            out += f"### `{c['name']}`\n\n"
            out += f"- **Archivo:** `{c['file']}`\n"
            out += f"- **Línea:** {c.get('line', '?')}\n"
            out += f"- **Hereda de:** {', '.join(c.get('bases', [])) or 'object'}\n"
            out += f"- **Métodos:** {len(c.get('methods', []))}\n"
            out += f"- **Documentada:** {'[OK] Sí' if c.get('docstring') else '[X] No'}\n\n"
            # Mostrar descripción de IA o docstring
            ai_desc = c.get("ai_description") or c.get("docstring")
            if ai_desc:
                out += f"> {ai_desc}\n\n"
            if c.get("methods"):
                out += "**Métodos:**\n\n"
                for m in c["methods"][:20]:
                    out += f"- `{m}()`\n"
                out += "\n"
            out += "---\n\n"
        return out

    # ─── 5. FUNCIONES ─────────────────────────────────────────────────────────
    def _function_docs(self) -> list:
        docs = []
        for fn in self.r.get("functions", []):
            params_doc = [{"name": p, "type": "any", "description": f"Parámetro {p}"}
                          for p in fn.get("params", [])]
            # Usar descripción de IA si está disponible, sino usar docstring
            description = fn.get("ai_description") or fn.get("docstring") or f"Función {fn['name']}"
            docs.append({
                "name":        fn["name"],
                "file":        fn["file"],
                "line":        fn.get("line"),
                "description": description,
                "parameters":  params_doc,
                "is_async":    fn.get("is_async", False),
                "complexity":  fn.get("complexity", 1),
                "returns":     {"type": "any", "description": "Valor de retorno"},
            })
        return docs

    def _functions_section(self) -> str:
        fns = self.r.get("functions", [])
        if not fns:
            return "## 5. Funciones\n\nNo se detectaron funciones.\n"

        # Agrupar por archivo
        by_file = {}
        for fn in fns:
            by_file.setdefault(fn.get("file", "desconocido"), []).append(fn)

        out = f"## 5. Documentación de Funciones\n\nTotal: **{len(fns)} funciones**\n\n"

        for fname, funcs in by_file.items():
            out += f"### Módulo: `{fname}`\n\n"
            for fn in funcs:
                params   = ", ".join(fn.get("params", [])) or "—"
                asyn     = "[ASYNC]" if fn.get("is_async") else "—"
                cx       = fn.get("complexity", 1)
                cx_icon  = "[LOW]" if cx <= 5 else "[MED]" if cx <= 10 else "[HIGH]"
                doc_icon = "[OK]" if fn.get("docstring") else "[X]"
                name     = ("async " if fn.get("is_async") else "") + fn["name"]
                out += f"**`{name}`**\n\n"
                out += f"- Parámetros: `{params}`\n"
                out += f"- Async: {asyn}\n"
                out += f"- Complejidad: {cx_icon} {cx}\n"
                out += f"- Documentada: {doc_icon}\n\n"
                # Mostrar descripción de IA o docstring
                ai_desc = fn.get("ai_description") or fn.get("docstring")
                if ai_desc:
                    out += f"> {ai_desc}\n\n"
            out += "---\n\n"

            # Detalle de funciones con docstring o descripción IA
            for fn in funcs:
                ai_desc = fn.get("ai_description") or fn.get("docstring")
                if ai_desc and fn.get("docstring"):
                    params_str = ", ".join(fn.get("params", []))
                    out += f"#### `{fn['name']}({params_str})`\n\n"
                    out += f"**Ubicación:** `{fn.get('file', 'desconocido')}`\n\n"
                    out += f"> {ai_desc}\n\n"
                    # Agregar ejemplo de código si está disponible
                    if fn.get("code_snippet"):
                        out += f"**Ejemplo de código:**\n\n```python\n{fn['code_snippet']}\n```\n\n"

        return out

    # ─── 6. MODELOS DE DATOS ──────────────────────────────────────────────────
    def _data_models(self) -> str:
        classes = self.r.get("classes", [])
        model_classes = [c for c in classes if any(
            kw in c["name"].lower() for kw in ["model", "schema", "entity", "dto", "dao"]
        )]

        out = "## 6. Modelos de Datos\n\n"
        if model_classes:
            out += f"Se detectaron **{len(model_classes)} modelos de datos**:\n\n"
            for m in model_classes:
                out += f"### `{m['name']}`\n"
                out += f"- Archivo: `{m['file']}`\n"
                out += f"- Hereda de: {', '.join(m.get('bases', [])) or 'object'}\n"
                out += f"- Métodos: {', '.join(m.get('methods', [])[:10])}\n\n"
        else:
            out += "No se detectaron clases con nombres de modelo explícitos.\n\n"
            out += "### Esquema General Inferido\n\n"
            out += "Basado en el análisis del código, las entidades principales son:\n\n"
            # Inferir entidades de los nombres de funciones/clases
            fns = self.r.get("functions", [])
            entities = set()
            for fn in fns:
                name = fn["name"].lower()
                for kw in ["get_", "create_", "update_", "delete_", "save_", "find_"]:
                    if name.startswith(kw):
                        entity = name.replace(kw, "").replace("_", " ").title()
                        if entity:
                            entities.add(entity)
            if entities:
                for e in list(entities)[:10]:
                    out += f"- **{e}**\n"
            else:
                out += "- No se pudieron inferir entidades del código fuente.\n"

        return out + "\n"

    # ─── 7. DESPLIEGUE ────────────────────────────────────────────────────────
    def _deployment(self) -> str:
        lang = self.r.get("primary_language", "Python")

        install_cmd = {
            "Python":     "pip install -r requirements.txt",
            "JavaScript": "npm install",
            "TypeScript": "npm install",
            "Java":       "mvn install",
            "Go":         "go mod download",
            "Ruby":       "bundle install",
            "PHP":        "composer install",
        }.get(lang, "# instalar dependencias")

        run_cmd = {
            "Python":     "python app.py",
            "JavaScript": "npm start",
            "TypeScript": "npm run build && npm start",
            "Java":       "mvn spring-boot:run",
            "Go":         "go run main.go",
        }.get(lang, "# ejecutar proyecto")

        return f"""## 7. Guía de Despliegue y Mantenimiento

### 7.1 Requisitos del Sistema

- **Lenguaje principal**: {lang}
- **Archivos detectados**: {self.r.get('total_files', 0)}

### 7.2 Instalación Local

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd <nombre-del-proyecto>

# 2. Instalar dependencias
{install_cmd}

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 4. Ejecutar el proyecto
{run_cmd}
```

### 7.3 Despliegue con Docker

```dockerfile
FROM {self._get_docker_base(lang)}

WORKDIR /app
COPY . .
RUN {install_cmd}
EXPOSE 8000
CMD ["{self._get_docker_cmd(lang)}"]
```

```bash
# Construir imagen
docker build -t mi-proyecto .

# Ejecutar contenedor
docker run -p 8000:8000 mi-proyecto
```

### 7.4 Variables de Entorno Recomendadas

```env
# General
APP_ENV=production
SECRET_KEY=clave-secreta-segura
DEBUG=False

# Base de datos
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mi_base_datos
DB_USER=usuario
DB_PASSWORD=contraseña

# API
API_VERSION=v1
ALLOWED_HOSTS=*
```

### 7.5 Checklist de Despliegue

- [ ] Variables de entorno configuradas
- [ ] Base de datos migrada
- [ ] Tests ejecutados y pasando
- [ ] Logs configurados
- [ ] HTTPS habilitado en producción
- [ ] Backups programados
- [ ] Monitoreo configurado

### 7.6 Registro de Cambios (Changelog)

**Versión 1.0.0** — {datetime.utcnow().strftime('%Y-%m-%d')}
- Versión inicial analizada por AutoDocs AI
- Documentación técnica generada automáticamente
- Análisis de calidad del código completado

"""

    def _get_docker_base(self, lang):
        return {"Python": "python:3.12-slim", "JavaScript": "node:20-slim",
                "TypeScript": "node:20-slim", "Java": "openjdk:17-slim",
                "Go": "golang:1.21-alpine"}.get(lang, "ubuntu:22.04")

    def _get_docker_cmd(self, lang):
        return {"Python": "python app.py", "JavaScript": "node index.js",
                "Go": "./main"}.get(lang, "start")

    # ─── 8. REPORTE DE CALIDAD ────────────────────────────────────────────────
    def _quality_report(self) -> str:
        fns    = self.r.get("functions", [])
        cls    = self.r.get("classes", [])
        score  = self.r.get("quality_score", 0)
        cx     = self.r.get("complexity", {})
        issues = self.r.get("issues", [])

        documented_fns  = sum(1 for f in fns if f.get("docstring"))
        documented_cls  = sum(1 for c in cls if c.get("docstring"))
        high_cx_fns     = [f for f in fns if f.get("complexity", 1) > 10]

        doc_pct = round(documented_fns / max(len(fns), 1) * 100)
        quality_label = "Excelente [GREEN]" if score >= 80 else "Bueno [YELLOW]" if score >= 60 else "Necesita mejoras [RED]"

        recommendations = []
        if doc_pct < 50:
            recommendations.append(f"- Agregar docstrings a las {len(fns) - documented_fns} funciones sin documentar")
        if high_cx_fns:
            names = ", ".join(f"`{f['name']}`" for f in high_cx_fns[:5])
            recommendations.append(f"- Refactorizar funciones con alta complejidad: {names}")
        if issues:
            recommendations.append(f"- Resolver {len(issues)} errores de análisis detectados")
        if not recommendations:
            recommendations.append("- El código tiene buena calidad general. ¡Mantén las buenas prácticas!")

        return f"""## 8. Reporte de Calidad del Código

### 8.1 Análisis de Métricas

**Score de Calidad:** {score}/100 ({quality_label})

**Distribución de Documentación:**
- Funciones documentadas: {documented_fns}/{len(fns)} ({doc_pct}%)
- Clases documentadas: {documented_cls}/{len(cls)}

**Análisis de Complejidad:**
- Complejidad promedio: {round(cx.get('avg', 1), 2)}
- Complejidad máxima: {cx.get('max', 0)}
- Funciones con alta complejidad (>10): {len(high_cx_fns)}

**Tendencia de Complejidad por Archivo:**
```text
[Gráfico de regresión lineal mostrando la tendencia de complejidad]
Eje X: Archivos ordenados por complejidad promedio
Eje Y: Score de complejidad
Tendencia: {"↑ Aumentando" if cx.get('avg', 1) > 5 else "→ Estable" if cx.get('avg', 1) > 2 else "↓ Baja"}
```

### 8.2 Funciones con Alta Complejidad Ciclomática

{"No hay funciones con complejidad > 10. [OK]" if not high_cx_fns else chr(10).join(
    f"- `{f['name']}` en `{f['file']}` — complejidad: **{f.get('complexity')}**"
    for f in high_cx_fns[:10]
)}

### 8.3 Recomendaciones

{chr(10).join(recommendations)}

### 8.4 Errores de Análisis

{"Sin errores detectados. [OK]" if not issues else chr(10).join(
    f"- `{i.get('file', '?')}`: {i.get('error', '?')}"
    for i in issues[:10]
)}
"""

    # ─── MARKDOWN COMPLETO ────────────────────────────────────────────────────
    def _full_markdown(self) -> str:
        separator = "\n\n---\n\n"
        return (
            self._readme()         + separator +
            self._architecture()   + separator +
            self._api_section()    + separator +
            self._classes_section()+ separator +
            self._functions_section()+ separator +
            self._data_models()    + separator +
            self._deployment()     + separator +
            self._quality_report() +
            f"\n\n---\n*Documentación generada automáticamente por AutoDocs AI — {self.now}*\n"
        )