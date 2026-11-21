from datetime import datetime
from services.ai_enhancer import AIEnhancer
from services import diagram_fallback
import subprocess
import os
import re
import shutil
import zlib
import struct
import base64
import mimetypes
import socket
import urllib.request
import urllib.error
from pathlib import Path

# Referencia diferida para evitar la importación circular con etl_pipeline.
# También permite sustituir el pipeline de forma controlada en las pruebas.
ETLPipeline = None

DOC_I18N = {
    'es': {
        'unknown': 'Desconocido',
        'project': 'Proyecto',
        'files': 'Archivos',
        'functions': 'Funciones',
        'classes': 'Clases',
        'endpoints': 'Endpoints',
        'excellent': 'Excelente',
        'acceptable': 'Aceptable',
        'needs_improvement': 'Requiere mejoras',
        'doc_title': 'Documentación del Proyecto',
        'scope_note': 'Alcance del documento.',
        'scope_text': 'Esta edición consolida los elementos identificados mediante el análisis estático del código fuente. Los valores reflejan el estado del proyecto al {now} y deben validarse frente al entorno de ejecución antes de una liberación productiva.',
        'exec_summary': '1.1 Resumen Ejecutivo',
        'stack': '1.2 Stack Tecnológico',
        'stats': '1.3 Estadísticas del Proyecto',
        'language': 'Lenguaje',
        'quantity': 'Cantidad',
        'metric': 'Métrica',
        'value': 'Valor',
        'total_files': 'Total de archivos',
        'api_endpoints': 'Endpoints API',
        'quality_score': 'Score de calidad',
        'documented_functions': 'Funciones documentadas',
        'documented_classes': 'Clases documentadas',
        'files_unit': '{c} archivos',
        'arch_title': '2. Documentación de Arquitectura y Diseño',
        'arch_intro': 'La presente sección describe la organización lógica y física observada en el repositorio. Los diagramas y patrones se derivan de los artefactos disponibles y constituyen una referencia para la comprensión y evolución del sistema.',
        'dir_structure': '2.1 Estructura de Directorios',
        'layer_dist': '2.2 Distribución por Capas',
        'lang_dist': '2.3 Distribución de Lenguajes',
        'infra_diagram': '2.4 Diagrama de Infraestructura',
        'usecase_diagram': '2.5 Diagrama de Casos de Uso',
        'class_diagram': '2.6 Diagrama de Clases',
        'patterns': '2.7 Patrones Detectados',
        'arch_insights': '2.8 Observaciones Complementarias de Arquitectura (Insights de Arquitectura)',
        'no_insights': 'No se dispone de observaciones complementarias para esta ejecución. La descripción precedente se basa exclusivamente en evidencia obtenida del código fuente.',
        'no_patterns': '- No se detectaron patrones específicos',
        'code_docs_title': '## 3. Documentación Técnica de Código',
        'no_endpoints': 'No se detectaron endpoints en este proyecto.',
        'env_setup': '### 3.1 Guía de Configuración del Entorno de Desarrollo',
        'endpoint_catalog': '### 3.2 Catálogo de Endpoints de API',
        'doc_status': '### 3.3 Estado de Comentarios y Docstrings',
        'test_plans': '### 3.4 Planes de Prueba',
        'classes_title': '## 4. Documentación de Clases y Módulos',
        'functions_title': '## 5. Documentación de Funciones',
        'data_models_title': '## 6. Modelos de Datos',
        'deployment_title': '## 7. Guía de Despliegue',
        'quality_title': '## 8. Reporte de Calidad',
        'method': 'Método', 'path': 'Ruta', 'file': 'Archivo', 'framework': 'Framework',
        'property': 'Propiedad', 'code_col': 'Código', 'description': 'Descripción', 'status': 'Estado',
        'success_op': 'Operación exitosa', 'bad_request': 'Solicitud incorrecta', 'unauthorized': 'No autorizado',
        'not_found': 'Recurso no encontrado', 'server_error': 'Error interno del servidor',
        'documented': 'Documentadas', 'undocumented': 'Sin documentar', 'total_functions': 'Total de funciones',
        'code_fragments': '#### Fragmentos de Código con Documentación',
        'need_docs': '#### Funciones que Requieren Documentación',
        'function_col': 'Función', 'params_col': 'Parámetros', 'file_col': 'Archivo',
        'test_function': 'Función de Test', 'complexity': 'Complejidad', 'implemented': 'Implementada',
        'no_tests': '> ⚠️ No se detectaron pruebas automatizadas en este proyecto.',
        'generated_by': 'Generado automáticamente por AutoDocs AI',
        'dominant_language': 'Lenguaje Dominante',
        'generation_date': 'Fecha de Generación',
        'generation_engine': 'Motor de Generación',
        'analyzed_files': 'Total Archivos Analizados',
        'cover_subtitle': 'Documento Maestro de Arquitectura, Endpoints, Modelos de Dominio y Métricas de Calidad',
        'cover_eyebrow': 'Auditoría & Especificación Técnica de Software',
        'cover_footer': 'Documento técnico confidencial · Generado automáticamente por AutoDocs AI · Distribución interna',
        'and_more': 'y {n} más',
        'primary_lang_label': 'El análisis del proyecto determinó que **{lang}** es el lenguaje predominante.',
    },
    'en': {
        'unknown': 'Unknown',
        'project': 'Project',
        'files': 'Files',
        'functions': 'Functions',
        'classes': 'Classes',
        'endpoints': 'Endpoints',
        'excellent': 'Excellent',
        'acceptable': 'Acceptable',
        'needs_improvement': 'Needs improvement',
        'doc_title': 'Project Documentation',
        'scope_note': 'Document scope.',
        'scope_text': 'This edition consolidates elements identified through static source code analysis. Values reflect the project state as of {now} and should be validated against the runtime environment before a production release.',
        'exec_summary': '1.1 Executive Summary',
        'stack': '1.2 Technology Stack',
        'stats': '1.3 Project Statistics',
        'language': 'Language',
        'quantity': 'Count',
        'metric': 'Metric',
        'value': 'Value',
        'total_files': 'Total files',
        'api_endpoints': 'API endpoints',
        'quality_score': 'Quality score',
        'documented_functions': 'Documented functions',
        'documented_classes': 'Documented classes',
        'files_unit': '{c} files',
        'arch_title': '2. Architecture and Design Documentation',
        'arch_intro': 'This section describes the logical and physical organization observed in the repository. Diagrams and patterns are derived from available artifacts and serve as a reference for understanding and evolving the system.',
        'dir_structure': '2.1 Directory Structure',
        'layer_dist': '2.2 Layer Distribution',
        'lang_dist': '2.3 Language Distribution',
        'infra_diagram': '2.4 Infrastructure Diagram',
        'usecase_diagram': '2.5 Use Case Diagram',
        'class_diagram': '2.6 Class Diagram',
        'patterns': '2.7 Detected Patterns',
        'arch_insights': '2.8 Additional Architecture Observations (Architecture Insights)',
        'no_insights': 'No additional observations are available for this run. The preceding description is based solely on evidence obtained from the source code.',
        'no_patterns': '- No specific patterns detected',
        'code_docs_title': '## 3. Technical Code Documentation',
        'no_endpoints': 'No endpoints were detected in this project.',
        'env_setup': '### 3.1 Development Environment Setup Guide',
        'endpoint_catalog': '### 3.2 API Endpoint Catalog',
        'doc_status': '### 3.3 Comments and Docstrings Status',
        'test_plans': '### 3.4 Test Plans',
        'classes_title': '## 4. Class and Module Documentation',
        'functions_title': '## 5. Function Documentation',
        'data_models_title': '## 6. Data Models',
        'deployment_title': '## 7. Deployment Guide',
        'quality_title': '## 8. Quality Report',
        'method': 'Method', 'path': 'Path', 'file': 'File', 'framework': 'Framework',
        'property': 'Property', 'code_col': 'Code', 'description': 'Description', 'status': 'Status',
        'success_op': 'Successful operation', 'bad_request': 'Bad request', 'unauthorized': 'Unauthorized',
        'not_found': 'Resource not found', 'server_error': 'Internal server error',
        'documented': 'Documented', 'undocumented': 'Undocumented', 'total_functions': 'Total functions',
        'code_fragments': '#### Documented Code Fragments',
        'need_docs': '#### Functions Requiring Documentation',
        'function_col': 'Function', 'params_col': 'Parameters', 'file_col': 'File',
        'test_function': 'Test Function', 'complexity': 'Complexity', 'implemented': 'Implemented',
        'no_tests': '> ⚠️ No automated tests were detected in this project.',
        'generated_by': 'Automatically generated by AutoDocs AI',
        'dominant_language': 'Dominant language',
        'generation_date': 'Generation date',
        'generation_engine': 'Generation engine',
        'analyzed_files': 'Total analyzed files',
        'cover_subtitle': 'Master Document of Architecture, Endpoints, Domain Models and Quality Metrics',
        'cover_eyebrow': 'Software Audit & Technical Specification',
        'cover_footer': 'Confidential technical document · Automatically generated by AutoDocs AI · Internal distribution',
        'and_more': 'and {n} more',
        'primary_lang_label': 'The project analysis determined that **{lang}** is the predominant language.',
    }
}

class DocGenerator:
    """
    Genera documentación técnica profesional completa:
    1. Arquitectura y Diseño
    2. Documentación de Código
    3. API Reference
    4. Guía de Despliegue
    5. Modelos de Datos
    """

    def __init__(self, analysis_results: dict, lang: str = None):
        self.r = analysis_results
        self.now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        raw_lang = lang or (analysis_results or {}).get('language') or (analysis_results or {}).get('doc_language') or 'es'
        raw_lang = str(raw_lang).lower()
        self.lang = 'en' if raw_lang.startswith('en') else 'es'

        # La clave de Groq debe estar configurada; ENABLE_AI_ANALYSIS permite desactivarla.
        use_ai = os.environ.get('ENABLE_AI_ANALYSIS', 'true').lower() == 'true'
        if use_ai:
            self.ai_enhancer = AIEnhancer()
            already_enhanced = bool(
                self.r.get('ai_documentation_enhanced')
                and (self.r.get('ai_output_language') == self.lang or not self.r.get('ai_output_language'))
            )
            if self.ai_enhancer.is_available() and not already_enhanced:
                # Pasar intención de idioma a la mejora si es posible
                try:
                    self.r = self.ai_enhancer.enhance_documentation(self.r, output_language=self.lang)
                except TypeError:
                    self.r = self.ai_enhancer.enhance_documentation(self.r)

    def t(self, key, **kwargs):
        d = DOC_I18N.get(self.lang, DOC_I18N['es'])
        text = d.get(key, DOC_I18N['es'].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def tx(self, spanish, english):
        """Texto inline con dos variantes; mantiene el diseño y cambia solo el idioma."""
        return english if self.lang == 'en' else spanish

    @staticmethod
    def _sanitize_ai_markdown(text: str) -> str:
        """Cierra bloques ``` abiertos por respuestas de IA cortadas."""
        if not text:
            return text
        fences = sum(1 for ln in text.splitlines() if ln.strip().startswith('```'))
        if fences % 2 == 1:
            text = text.rstrip() + "\n```"
        return text

    # ─── Descripciones largas y claras ────────────────────────────────────────
    MIN_LONG_DESCRIPTION_WORDS = 60

    @staticmethod
    def _name_list(items, limit: int = 6, suffix: str = ""):
        """Devuelve (['`a`', '`b`'], cuántos_más) a partir de nombres o dicts con 'name'."""
        names = []
        for it in items or []:
            name = it.get("name") if isinstance(it, dict) else it
            if name:
                names.append(f"`{name}{suffix}`")
        return names[:limit], max(len(names) - limit, 0)

    def _plain_explanation(self, kind: str, item: dict) -> str:
        """Explicación larga, en palabras sencillas, armada con los datos del análisis."""
        name = item.get("name") or item.get("path") or "?"
        file = item.get("file")
        line = item.get("line")
        parts = []

        def where(es_word, en_word):
            if not file:
                return ""
            at = self.tx(f", en la línea {line}", f", at line {line}") if line else ""
            return self.tx(
                f"{es_word} `{file}`{at}.",
                f"{en_word} `{file}`{at}.",
            )

        if kind in ("model", "class"):
            if kind == "model":
                parts.append(self.tx(
                    f"El modelo **{name}** representa un tipo de información que el sistema necesita guardar y consultar, como si fuera una ficha con varios datos bien ordenados.",
                    f"The **{name}** model represents a kind of information the system needs to store and look up, like a card with several well-organized pieces of data.",
                ))
            else:
                parts.append(self.tx(
                    f"La clase **{name}** reúne en un solo lugar datos y acciones que están relacionados entre sí, para que el resto del programa los use sin repetir el mismo trabajo.",
                    f"The **{name}** class gathers related data and actions in one place so the rest of the program can use them without repeating work.",
                ))
            loc = where("Se encuentra en el archivo", "It is located in the file")
            if loc:
                parts.append(loc)
            bases = [b for b in (item.get("bases") or []) if b and b != "object"]
            if bases:
                bl = ", ".join(f"`{b}`" for b in bases)
                parts.append(self.tx(
                    f"Parte de {bl}, así que ya hereda de ahí varias características y solo añade lo que le es propio.",
                    f"It builds on {bl}, so it already inherits several features from there and only adds what is specific to it.",
                ))
            fields, more_f = self._name_list(item.get("fields"))
            if fields:
                n = len(fields) + more_f
                tail_es = f" y {more_f} más" if more_f else ""
                tail_en = f" and {more_f} more" if more_f else ""
                parts.append(self.tx(
                    f"Guarda {n} {'dato' if n == 1 else 'datos'}: {', '.join(fields)}{tail_es}.",
                    f"It stores {n} {'field' if n == 1 else 'fields'}: {', '.join(fields)}{tail_en}.",
                ))
            methods, more_m = self._name_list(item.get("methods"), limit=5, suffix="()")
            if methods:
                m = len(methods) + more_m
                tail_es = f" y {more_m} más" if more_m else ""
                tail_en = f" and {more_m} more" if more_m else ""
                parts.append(self.tx(
                    f"Además ofrece {m} {'acción' if m == 1 else 'acciones'} que se pueden ejecutar sobre él, por ejemplo {', '.join(methods)}{tail_es}.",
                    f"It also offers {m} {'action' if m == 1 else 'actions'} that can be run on it, for example {', '.join(methods)}{tail_en}.",
                ))
            parts.append(self.tx(
                f"En palabras simples, sirve para mantener ordenado todo lo relacionado con **{name}**, de modo que cualquier parte de la aplicación pueda consultarlo o actualizarlo de forma segura.",
                f"In simple terms, it keeps everything related to **{name}** organized so any part of the application can read or update it safely.",
            ))

        elif kind == "function":
            parts.append(self.tx(
                f"La función `{name}` realiza una tarea concreta dentro del sistema, de modo que otras partes del programa puedan pedirla sin conocer cómo funciona por dentro.",
                f"The `{name}` function performs a specific task inside the system, so other parts of the program can request it without knowing how it works internally.",
            ))
            loc = where("Está en el archivo", "It is in the file")
            if loc:
                parts.append(loc)
            params, more_p = self._name_list(item.get("params"))
            if params:
                n = len(params) + more_p
                parts.append(self.tx(
                    f"Para trabajar necesita recibir {n} {'dato' if n == 1 else 'datos'}: {', '.join(params)}.",
                    f"To work, it needs to receive {n} {'input' if n == 1 else 'inputs'}: {', '.join(params)}.",
                ))
            else:
                parts.append(self.tx("No necesita recibir datos para trabajar.", "It does not need any input to work."))
            if item.get("is_async"):
                parts.append(self.tx(
                    "Es asíncrona: puede esperar una respuesta sin detener el resto del programa.",
                    "It is asynchronous: it can wait for a response without stopping the rest of the program.",
                ))
            cx = item.get("complexity", 1) or 1
            if cx > 10:
                parts.append(self.tx(
                    f"Tiene muchos caminos de decisión (complejidad {cx}), por lo que conviene revisarla con cuidado antes de modificarla.",
                    f"It has many decision paths (complexity {cx}), so it should be reviewed carefully before changing it.",
                ))
            elif cx > 5:
                parts.append(self.tx(
                    f"Tiene un nivel de complejidad moderado ({cx}), con varios caminos de decisión.",
                    f"It has a moderate level of complexity ({cx}), with several decision paths.",
                ))
            else:
                parts.append(self.tx(
                    f"Es fácil de seguir (complejidad {cx}) porque tiene pocos caminos de decisión.",
                    f"It is easy to follow (complexity {cx}) because it has few decision paths.",
                ))

        elif kind == "endpoint":
            method = str(item.get("method", "GET")).upper()
            path = item.get("path", "")
            verbs = {
                "GET": ("consulta información sin modificarla", "reads information without changing it"),
                "POST": ("recibe datos nuevos para crear o procesar algo", "receives new data to create or process something"),
                "PUT": ("reemplaza información que ya existe", "replaces information that already exists"),
                "PATCH": ("actualiza una parte de información que ya existe", "updates part of existing information"),
                "DELETE": ("elimina información", "removes information"),
            }
            es_v, en_v = verbs.get(method, ("atiende una solicitud de la aplicación", "handles a request from the application"))
            parts.append(self.tx(
                f"El endpoint `{method} {path}` es una puerta de entrada de la API: {es_v}.",
                f"The `{method} {path}` endpoint is an entry point of the API: it {en_v}.",
            ))
            loc = where("Está definido en el archivo", "It is defined in the file")
            if loc:
                parts.append(loc)
            fw = item.get("framework")
            if fw and fw not in ("desconocido", "unknown", "Desconocido", "Unknown"):
                parts.append(self.tx(f"Usa el framework {fw}.", f"It uses the {fw} framework."))
            parts.append(self.tx(
                "Al terminar responde con un código que indica si todo salió bien (200) o si hubo un problema: datos incorrectos (400), falta de permisos (401), recurso inexistente (404) o error interno (500).",
                "When it finishes it replies with a code telling whether everything went well (200) or there was a problem: invalid data (400), missing permissions (401), resource not found (404) or internal error (500).",
            ))
        return " ".join(p for p in parts if p)

    _PLACEHOLDER_RE = re.compile(
        r"^(?:(?:modelo|clase|función|funcion|class|function|model|endpoint)\b.{0,60}"
        r"|modelo de datos que representa.*|data model representing.*)$",
        flags=re.IGNORECASE | re.DOTALL,
    )

    @classmethod
    def _is_placeholder_description(cls, text: str) -> bool:
        """True para los textos genéricos de relleno («Modelo X», «Clase X», «Endpoint GET /x»…)."""
        text = (text or "").strip()
        if not text:
            return True
        words = text.split()
        if text.lower().startswith(("modelo de datos que representa", "data model representing")):
            return True
        return len(words) <= 5 and bool(cls._PLACEHOLDER_RE.match(text))

    def _long_description(self, kind: str, item: dict, base: str = "") -> str:
        """
        Devuelve una descripción larga y clara. Si ya existe una descripción extensa
        (por ejemplo la generada por la IA) se respeta; si es corta o es solo un texto
        de relleno ("Modelo X"), se completa con una explicación en palabras sencillas.
        """
        base = (base or "").strip()
        if len(base.split()) >= self.MIN_LONG_DESCRIPTION_WORDS:
            return base
        if self._is_placeholder_description(base):
            base = ""
        extra = self._plain_explanation(kind, item)
        if base and not base.endswith(('.', '!', '?', '`', '```')):
            base += "."
        return f"{base}\n\n{extra}".strip() if base and extra else (base or extra)

    def _description_quote(self, text: str) -> str:
        """Convierte un texto de varios párrafos en un único bloque de cita."""
        lines = (text or "").strip().splitlines()
        if not lines:
            return ""
        quoted = [f"> **{self.t('description')}:** {lines[0]}"]
        quoted += [f"> {ln}" if ln.strip() else ">" for ln in lines[1:]]
        return "\n".join(quoted) + "\n\n"

    @staticmethod
    def _color_bar_html(hex_color: str, alt: str = "Nivel de calidad") -> str:
        """
        Barra de color como imagen PNG (data URI) generada sin librerías externas.
        Se usa <img> porque es la única etiqueta HTML que el conversor respeta.
        """
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        # Imagen ya con forma de barra (600x8): el conversor respeta la proporción
        # de la imagen e ignora el width/height del style.
        w, h = 600, 8
        row = b'\x00' + bytes([r, g, b]) * w
        raw = row * h

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack('>I', len(data)) + tag + data
                    + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

        png = (b'\x89PNG\r\n\x1a\n'
               + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(raw))
               + chunk(b'IEND', b''))
        uri = 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')
        return (
            f"\n<div style=\"margin: 0.4rem 0 0.6rem 0;\">"
            f"<img src=\"{uri}\" alt=\"{alt}\" "
            f"style=\"width: 100%; height: 6px; border-radius: 3px; display:block;\">"
            f"</div>\n"
        )

    def _render_markdown_table(self, headers: list[str], rows: list[list[str]]) -> str:
        header_line = '| ' + ' | '.join(headers) + ' |'
        separator_line = '| ' + ' | '.join('---' for _ in headers) + ' |'
        row_lines = '\n'.join('| ' + ' | '.join(row) + ' |' for row in rows)
        return f"{header_line}\n{separator_line}\n{row_lines}\n"

    @staticmethod
    def _count_function_loc(fn: dict):
        """
        Cuenta las líneas de código de una función a partir de su código fuente.

        - Si existe `code_snippet`, se cuentan sus líneas no vacías.
        - Si no hay snippet pero el análisis aporta `line` y `end_line`
          (o `end_lineno`), se usa ese rango.
        - Si no hay datos suficientes devuelve None (se muestra «—»).
        """
        snippet = fn.get('code_snippet') or ''
        if snippet.strip():
            return sum(1 for ln in snippet.splitlines() if ln.strip())

        start = fn.get('line')
        end = fn.get('end_line') or fn.get('end_lineno')
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            return end - start + 1
        return None

    def _graphviz_available(self) -> bool:
        return bool(shutil.which('dot'))

    def _get_plantuml_command(self, temp_file: Path, output_dir: Path):
        if not self._graphviz_available():
            # Sin Graphviz, PlantUML puede dibujar igual con su motor de diseño interno (Smetana)
            self._use_smetana = True

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
        # PlantText es el renderizador solicitado; PlantUML oficial y Kroki quedan como respaldo.
        default_servers = [
            'https://www.planttext.com/plantuml',
            'https://www.plantuml.com/plantuml',
        ]
        server_url = os.environ.get('PLANTUML_SERVER_URL')
        servers = [server_url] + default_servers if server_url else default_servers
        encoded = self._plantuml_encode(plantuml_code)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/png,*/*;q=0.8',
        }
        if getattr(self, '_remote_diagrams_down', False):
            return None  # ya se comprobó que no hay red: no se espera de nuevo por cada diagrama
        reached_a_server = False
        for server in filter(None, servers):
            for path_variant in ['png', 'svg']:
                ext = 'png' if path_variant == 'png' else 'svg'
                target_url = f"{server.rstrip('/')}/{path_variant}/{encoded}"
                output_path = output_file.with_suffix(f'.{ext}')
                try:
                    request = urllib.request.Request(target_url, headers=headers)
                    with urllib.request.urlopen(request, timeout=6) as response:
                        reached_a_server = True
                        if response.status != 200:
                            continue
                        content = response.read()
                        if ext == 'png':
                            if not content.startswith(b'\x89PNG\r\n\x1a\n'):
                                continue
                        elif ext == 'svg':
                            text = content.decode('utf-8', errors='ignore').strip()
                            if not (text.startswith('<svg') or text.startswith('<?xml')):
                                continue
                        output_path.write_bytes(content)
                        if self._is_valid_image(output_path):
                            return output_path
                        output_path.unlink(missing_ok=True)
                except urllib.error.HTTPError:
                    reached_a_server = True  # el servidor respondió (con error): probar la otra variante
                except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError):
                    break  # servidor inalcanzable: no probar su otra variante
                except Exception:
                    pass

        # 2. Fallback a Kroki vía POST
        try:
            kroki_req = urllib.request.Request(
                "https://kroki.io/plantuml/png",
                data=plantuml_code.encode("utf-8"),
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "image/png"
                },
                method="POST"
            )
            with urllib.request.urlopen(kroki_req, timeout=8) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) > 200:
                        png_out = output_file.with_suffix('.png')
                        png_out.write_bytes(data)
                        if self._is_valid_image(png_out):
                            return png_out
                        png_out.unlink(missing_ok=True)
        except urllib.error.HTTPError:
            reached_a_server = True
        except Exception:
            pass
        if not reached_a_server:
            self._remote_diagrams_down = True
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

            self._use_smetana = False
            cmd = self._get_plantuml_command(temp_file, output_dir_path)
            if cmd and self._use_smetana:
                temp_file.write_text(
                    plantuml_code.replace('@startuml', '@startuml\n!pragma layout smetana', 1),
                    encoding='utf-8',
                )
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
            return self._offline_or_link(plantuml_code)
        except Exception as e:
            print(f"[PlantUML Error] {e}")
            try:
                return self._offline_or_link(plantuml_code)
            except Exception:
                return ""

    def _offline_or_link(self, plantuml_code: str) -> str:
        """Dibuja el diagrama localmente; solo si no se puede, devuelve el enlace externo."""
        png = diagram_fallback.render_png(plantuml_code)
        if png:
            return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')
        encoded = self._plantuml_encode(plantuml_code)
        return f"https://www.planttext.com/plantuml/png/{encoded}"

    def _render_diagram_block(self, title: str, plantuml_code: str) -> str:
        """
        Genera el bloque HTML de un diagrama integrado con PlantText:
        1. Muestra la imagen generada (data URI o URL directa de PlantText).
        2. Añade un botón/enlace interactivo para abrir y editar el diagrama en https://www.planttext.com/.
        3. Mantiene intacto el diseño y estilo existente.
        """
        diagram_src = self._generate_plantuml_diagram(plantuml_code)
        encoded = self._plantuml_encode(plantuml_code)
        if not diagram_src:
            diagram_src = f"https://www.planttext.com/plantuml/png/{encoded}"

        editor_url = f"https://www.planttext.com/?text={encoded}"
        editor_label = self.tx("Abrir y editar diagrama en PlantText", "Open and edit diagram in PlantText")

        return (
            f'\n\n<img src="{diagram_src}" alt="{title}">\n\n'
            f'[🔗 {editor_label}]({editor_url})\n\n'
        )

    def generate(self) -> dict:
        readme = self._readme()
        architecture = self._architecture()
        api_docs = self._api_docs()
        class_docs = self._class_docs()
        function_docs = self._function_docs()
        data_models = self._data_models()
        deployment = self._deployment()
        quality_report = self._quality_report()
        full_markdown = self._full_markdown({
            "readme": readme,
            "architecture": architecture,
            "api_section": self._api_section(),
            "classes_section": self._classes_section(),
            "functions_section": self._functions_section(),
            "data_models": data_models,
            "deployment": deployment,
            "quality_report": quality_report,
            "data_analysis": self._data_analysis_section(),
        })

        return {
            "generated_at": self.now,
            "readme": readme,
            "architecture": architecture,
            "api_docs": api_docs,
            "class_docs": class_docs,
            "function_docs": function_docs,
            "data_models": data_models,
            "deployment": deployment,
            "quality_report": quality_report,
            "full_markdown": full_markdown,
        }

    # ─── 1. README ────────────────────────────────────────────────────────────
    def _cover_page(self) -> str:
        lang  = self.r.get("primary_language", self.t('unknown'))
        langs = self.r.get("languages", {})
        fns   = self.r.get("functions", [])
        cls   = self.r.get("classes", [])
        eps   = self.r.get("endpoints", [])
        files = self.r.get("total_files", 0)
        score = self.r.get("quality_score", 0)
        label = self.t('excellent') if score >= 80 else self.t('acceptable') if score >= 60 else self.t('needs_improvement')

        return f"""
        <div class="cover">
          <p class="eyebrow">{self.t('cover_eyebrow')}</p>
          <h1 class="cover-title">{self.r.get('project_name', self.t('project'))}</h1>
          <div class="cover-rule"></div>
          <p class="cover-subtitle">
            {self.t('cover_subtitle')}
          </p>

          <table class="meta-table">
            <tr><td>{self.t('project')}:</td><td><strong>{self.r.get('project_name','—')}</strong></td></tr>
            <tr><td>{self.t('dominant_language')}:</td><td><strong>{lang}</strong></td></tr>
            <tr><td>{self.t('quality_score')}:</td><td><strong>{score} / 100 ({label})</strong></td></tr>
            <tr><td>{self.t('analyzed_files')}:</td><td><strong>{files}</strong></td></tr>
            <tr><td>{self.t('generation_date')}:</td><td><strong>{self.now}</strong></td></tr>
            <tr><td>{self.t('generation_engine')}:</td><td><strong>AutoDocs AI Enterprise (Groq AI + PlantUML/Kroki)</strong></td></tr>
          </table>

          <div class="kpi-row">
            <div class="kpi"><span class="kpi-num">{files}</span><span class="kpi-lbl">{self.t('files')}</span></div>
            <div class="kpi"><span class="kpi-num">{len(fns)}</span><span class="kpi-lbl">{self.t('functions')}</span></div>
            <div class="kpi"><span class="kpi-num">{len(cls)}</span><span class="kpi-lbl">{self.t('classes')}</span></div>
            <div class="kpi"><span class="kpi-num">{len(eps)}</span><span class="kpi-lbl">{self.t('endpoints')}</span></div>
          </div>

          <p class="cover-footer">
            {self.t('cover_footer')}
          </p>
        </div>
        <div class="page-break"></div>
        """
    def _readme(self) -> str:
        lang   = self.r.get("primary_language", self.t('unknown'))
        langs  = self.r.get("languages", {})
        fns    = self.r.get("functions", [])
        cls    = self.r.get("classes", [])
        eps    = self.r.get("endpoints", [])
        files  = self.r.get("total_files", 0)
        score  = self.r.get("quality_score", 0)

        lang_rows = [[l, self.t('files_unit', c=c)] for l, c in langs.items()]
        metrics_rows = [
            [self.t('total_files'), str(files)],
            [self.t('functions'), str(len(fns))],
            [self.t('classes'), str(len(cls))],
            [self.t('api_endpoints'), str(len(eps))],
            [self.t('quality_score'), f"{score}/100"],
            [self.t('documented_functions'), f"{sum(1 for f in fns if f.get('docstring'))} / {len(fns)}"],
            [self.t('documented_classes'), f"{sum(1 for c in cls if c.get('docstring'))} / {len(cls)}"],
        ]

        if self.lang == 'en':
            exec_summary = f"""The project analysis determined that **{lang}** is the predominant language.
The examined scope includes **{files} source files**, **{len(fns)} functions**,
**{len(cls)} classes** and **{len(eps)} API endpoints**. The automated evaluation
assigns the code a quality score of **{score}/100**. The following sections
develop these findings from the perspective of architecture, interfaces,
components, data, deployment and maintainability."""
            stack_intro = "The following distribution identifies the repository's technology composition and helps estimate maintenance effort by language."
            stats_intro = "These metrics summarize the detected technical inventory. If an element is absent, it means the analyzer did not identify it statically; it does not necessarily mean the capability does not exist at runtime."
        else:
            exec_summary = f"""El análisis del proyecto determinó que **{lang}** es el lenguaje predominante.
El alcance examinado comprende **{files} archivos fuente**, **{len(fns)} funciones**,
**{len(cls)} clases** y **{len(eps)} endpoints de API**. La evaluación automatizada
asigna al código un resultado de calidad de **{score}/100**. Las secciones siguientes
desarrollan estos hallazgos desde la perspectiva de arquitectura, interfaces,
componentes, datos, despliegue y mantenibilidad."""
            stack_intro = "La distribución siguiente permite identificar la composición tecnológica del repositorio y dimensionar el esfuerzo de mantenimiento por lenguaje."
            stats_intro = "Las métricas resumen el inventario técnico detectado. La ausencia de un elemento indica que el analizador no lo identificó de forma estática; no implica necesariamente que la capacidad no exista durante la ejecución."

        return f"""# {self.t('doc_title')}

> **{self.t('scope_note')}** {self.t('scope_text', now=self.now)}

## {self.t('exec_summary')}

{exec_summary}

## {self.t('stack')}

{stack_intro}

{self._render_markdown_table([self.t('language'), self.t('quantity')], lang_rows)}

## {self.t('stats')}

{stats_intro}

{self._render_markdown_table([self.t('metric'), self.t('value')], metrics_rows)}
"""

    # ─── 2. ARQUITECTURA ──────────────────────────────────────────────────────
    def _architecture(self) -> str:
        struct  = self.r.get("structure", [])
        langs   = self.r.get("languages", {})
        eps     = self.r.get("endpoints", [])
        cls     = self.r.get("classes", [])
        
        # Agregar insights de IA si están disponibles (cerrando bloques ``` abiertos)
        ai_insights = self._sanitize_ai_markdown(self.r.get("ai_architecture_insights", ""))

        # Agrupar por directorio raíz
        dirs = {}
        for item in struct:
            parts = item["path"].replace("\\", "/").split("/")
            top = parts[0] if len(parts) > 1 else self.tx("(raíz)", "(root)")
            dirs.setdefault(top, []).append(item)

        dir_section = ""
        for d, items in list(dirs.items())[:20]:
            exts = {}
            for i in items:
                ext = i["name"].rsplit(".", 1)[-1] if "." in i["name"] else self.tx("sin ext", "no ext")
                exts[ext] = exts.get(ext, 0) + 1
            ext_str = ", ".join(f".{e}({n})" for e, n in exts.items())
            files_label = self.tx("archivos", "files")
            dir_section += f"- **`{d}/`** — {len(items)} {files_label} [{ext_str}]\n"

        file_lines = self._file_lines_section()
        files_word = self.tx('archivos', 'files')
        lang_dist = "\n".join(
            f"- {l}: {c} {files_word} ({round(c/max(sum(langs.values()),1)*100)}%)"
            for l, c in sorted(langs.items(), key=lambda x: -x[1])
        )

        # Diagrama de casos de uso en PlantUML
        use_cases_puml = "@startuml\n"
        use_cases_puml += "left to right direction\n"
        use_cases_puml += "skinparam packageStyle rectangle\n"
        use_cases_puml += f"actor \"{self.tx('Usuario', 'User')}\" as user\n"
        use_cases_puml += f"rectangle \"{self.tx('Sistema', 'System')}\" {{\n"
        for idx, ep in enumerate(eps[:10], start=1):
            method = ep.get("method", "GET")
            path_label = ep.get("path", "/").replace('"', '')
            use_cases_puml += f'  usecase "{method} {path_label}" as uc_{idx}\n'
            use_cases_puml += f'  user --> uc_{idx}\n'
        if len(eps) > 10:
            use_cases_puml += f'  usecase "{self.tx("Otros endpoints", "Other endpoints")}" as uc_other\n'
            use_cases_puml += '  user --> uc_other\n'
        use_cases_puml += "}\n@enduml"
        
        # Generar diagrama de casos de uso
        use_case_diagram = ""
        if eps:
            use_case_diagram = self._render_diagram_block(self.tx('Diagrama de Casos de Uso', 'Use Case Diagram'), use_cases_puml)

        # Diagrama de infraestructura en PlantUML
        infra_puml = f"""@startuml
skinparam componentStyle rectangle
package "{self.tx('Cliente / Frontend', 'Client / Frontend')}" {{
  [{self.tx('Navegador', 'Browser')}] as browser
  [{self.tx('App Móvil', 'Mobile app')}] as mobile
  [CLI] as cli
}}
package "{self.tx('API / Backend', 'API / Backend')}" {{
  [{self.tx('Rutas', 'Routes')}] as routes
  [{self.tx('Lógica de Negocio', 'Business logic')}] as logic
  routes --> logic
}}
database "{self.tx('Base de Datos', 'Database')}" as db
database "{self.tx('Caché', 'Cache')}" as cache
[{self.tx('Servicios Ext.', 'External services')}] as ext
logic --> db
logic --> cache
logic --> ext
browser --> routes
mobile --> routes
cli --> routes
@enduml"""
        
        # Generar diagrama de infraestructura
        infra_diagram = self._render_diagram_block(self.tx('Diagrama de Infraestructura', 'Infrastructure Diagram'), infra_puml)

        # Diagrama de clases en PlantUML
        class_puml = "@startuml\n"
        class_puml += "skinparam classAttributeIconSize 0\n"
        for idx, c in enumerate(cls[:15], start=1):
            class_name = c.get("name", f"Class{idx}")
            safe_alias = f"cls_{idx}"
            class_puml += f'class "{class_name}" as {safe_alias} {{\n'
            methods = c.get("methods", [])
            for m in methods[:5]:
                clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(m))
                if clean_m:
                    class_puml += f'  +{clean_m}()\n'
            if len(methods) > 5:
                class_puml += f'  ... ({len(methods) - 5} {self.tx("más", "more")})\n'
            class_puml += '}\n'
        class_puml += "@enduml"
        
        # Detectar clases "básicas" (sin métodos ni atributos)
        basic_classes = [c for c in cls if not c.get("methods") and not c.get("attributes")]
        basic_class_warning = ""
        if basic_classes:
            names = ", ".join(f"`{c.get('name', '?')}`" for c in basic_classes[:10])
            extra_n = len(basic_classes) - 10
            extra = (f" and {extra_n} more" if self.lang == 'en' else f" y {extra_n} más") if extra_n > 0 else ""
            if self.lang == 'en':
                basic_class_warning = (
                    f"\n\n> ⚠️ **Classes with incomplete information:** The following classes appear without documented methods or attributes: "
                    f"{names}{extra}. "
                    f"To display the diagram correctly, add methods, properties or docstrings to these classes in your source code and regenerate the documentation.\n"
                )
            else:
                basic_class_warning = (
                    f"\n\n> ⚠️ **Clases con información incompleta:** Las siguientes clases aparecen sin métodos ni atributos documentados: "
                    f"{names}{extra}. "
                    f"Para que el diagrama se visualice correctamente, agrega métodos, propiedades o docstrings a estas clases en tu código fuente y regenera la documentación.\n"
                )

        # Generar diagrama de clases
        class_diagram = ""
        if cls:
            class_diagram = self._render_diagram_block(self.tx('Diagrama de Clases', 'Class Diagram'), class_puml)
            class_diagram += basic_class_warning

        root_name = 'project' if self.lang == 'en' else 'proyecto'
        return f"""## {self.t('arch_title')}

{self.t('arch_intro')}

### {self.t('dir_structure')}

```
{root_name}/
{chr(10).join(f'├── {d}/' for d in list(dirs.keys())[:15])}
```

{file_lines}

### {self.t('layer_dist')}

{dir_section}

### {self.t('lang_dist')}

{lang_dist}

### {self.t('infra_diagram')}

{infra_diagram}

{self.tx(
    "La infraestructura muestra la interacción entre el cliente, las rutas de la API, la lógica de negocio, los datos y los servicios externos.",
    "The infrastructure view shows interactions between the client, API routes, business logic, data stores, and external services."
)}

### {self.t('usecase_diagram')}

{use_case_diagram}

{self.tx(
    "El diagrama de casos de uso relaciona al usuario con las operaciones expuestas por los endpoints detectados.",
    "The use case diagram relates users to the operations exposed by the detected endpoints."
) if eps else self.t('no_endpoints')}

### {self.t('class_diagram')}

{class_diagram}

{self.tx(
    "El diagrama resume las clases detectadas, sus métodos principales y las relaciones estructurales disponibles.",
    "The diagram summarizes detected classes, their main methods, and the structural relationships available."
) if cls else self.tx(
    "No se detectaron clases suficientes para generar este diagrama.",
    "Not enough classes were detected to generate this diagram."
)}

### {self.t('patterns')}

{self._detect_patterns()}

### {self.t('arch_insights')}

{ai_insights if ai_insights else self.t('no_insights')}
"""

    def _file_lines_section(self) -> str:
        rows = []
        total_lines = 0
        counted_files = 0
        project_path = self.r.get("project_path")
        for item in self.r.get("structure", []):
            path = item.get("path") or item.get("name")
            if not path:
                continue
            line_count = item.get("line_count")
            if not (type(line_count) is int and line_count >= 0):
                # Intentar leer desde el disco si está disponible el proyecto
                if project_path:
                    try:
                        p = Path(project_path) / path
                        if p.is_file():
                            line_count = len(p.read_bytes().split(b'\n'))
                            item["line_count"] = line_count
                    except Exception:
                        pass
                if not (type(line_count) is int and line_count >= 0):
                    try:
                        p = Path(path)
                        if p.is_file():
                            line_count = len(p.read_bytes().split(b'\n'))
                            item["line_count"] = line_count
                    except Exception:
                        pass

            if type(line_count) is int and line_count >= 0:
                total_lines += line_count
                counted_files += 1
                line_count_text = str(line_count)
            else:
                line_count_text = "—"
            rows.append([f"`{path}`", line_count_text])

        title = self.tx("2.1.1 Líneas por archivo analizado", "2.1.1 Lines per analyzed file")
        if not rows:
            return f"### {title}\n\n{self.tx('No hay archivos analizados para mostrar.', 'There are no analyzed files to display.')}\n"

        table = self._render_markdown_table(
            [self.t('file'), self.tx('Líneas de código', 'Lines of code')],
            rows,
        )
        total_label = self.tx('Total de líneas de archivos contadas', 'Total analyzed file lines')
        return f"### {title}\n\n{table}\n**{total_label}:** {total_lines} ({counted_files}/{len(rows)} {self.tx('archivos', 'files')})\n"

    def _detect_patterns(self) -> str:
        eps   = self.r.get("endpoints", [])
        cls   = self.r.get("classes", [])
        fns   = self.r.get("functions", [])
        patterns = []

        if eps:
            frameworks = set(e.get("framework", "") for e in eps)
            if self.lang == 'en':
                patterns.append(f"- **REST API**: {len(eps)} endpoints detected ({', '.join(frameworks)})")
            else:
                patterns.append(f"- **API REST**: {len(eps)} endpoints detectados ({', '.join(frameworks)})")
        if any("Model" in c["name"] or "model" in c["name"].lower() for c in cls):
            patterns.append("- **MVC Pattern**: Model classes detected" if self.lang == 'en' else "- **Patrón MVC**: clases Model detectadas")
        if any("test" in f["name"].lower() or "Test" in f["name"] for f in fns):
            tc = sum(1 for f in fns if "test" in f["name"].lower())
            patterns.append(f"- **Testing**: {tc} test functions detected" if self.lang == 'en' else f"- **Testing**: {tc} funciones de prueba detectadas")
        if any("__init__" in f["name"] for f in fns):
            patterns.append("- **Object-Oriented Programming**: constructors detected" if self.lang == 'en' else "- **Programación Orientada a Objetos**: constructores detectados")
        async_fns = sum(1 for f in fns if f.get("is_async"))
        if async_fns:
            patterns.append(f"- **Asynchronous Programming**: {async_fns} async/await functions" if self.lang == 'en' else f"- **Programación Asíncrona**: {async_fns} funciones async/await")

        return "\n".join(patterns) if patterns else self.t('no_patterns')

    # ─── 3. API DOCS ──────────────────────────────────────────────────────────
    def _api_docs(self) -> list:
        docs = []
        for ep in self.r.get("endpoints", []):
            description = ep.get("ai_description") or f"Endpoint {ep.get('method')} {ep.get('path')}"
            docs.append({
                "method":      ep.get("method"),
                "path":        ep.get("path"),
                "file":        ep.get("file"),
                "framework":   ep.get("framework"),
                "description": description,
                "parameters":  [],
                "responses": {
                    "200": {"description": self.tx("Operación exitosa", "Successful operation")},
                    "400": {"description": self.tx("Solicitud incorrecta", "Bad request")},
                    "401": {"description": self.tx("No autorizado", "Unauthorized")},
                    "404": {"description": self.tx("Recurso no encontrado", "Resource not found")},
                    "500": {"description": self.tx("Error interno del servidor", "Internal server error")},
                }
            })
        return docs

    def _render_code_fragment(self, name: str, file: str, snippet: str, explanation: str, lang: str = "python") -> str:
        """Genera un bloque HTML de fragmento de código con explicación."""
        if not snippet:
            return ""
        # Escapar caracteres problemáticos en el snippet para HTML
        safe_snippet = snippet.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        return f"""
<div class="code-fragment">
  <div class="code-fragment-header">
    <div class="frag-icon">&lt;/&gt;</div>
    <div>
      <div class="frag-title">{name}</div>
      <div class="frag-file">{file}</div>
    </div>
  </div>
  <pre><code>{safe_snippet}</code></pre>
  <div class="code-explanation">{explanation}</div>
</div>
"""

    def _generate_code_explanation(self, fn: dict) -> str:
        """Genera una explicación automática de un fragmento de código."""
        name = fn.get('name', '?')
        params = fn.get('params', [])
        docstring = fn.get('docstring', '')
        is_async = fn.get('is_async', False)
        cx = fn.get('complexity', 1)

        purpose = self.tx('Propósito', 'Purpose')
        parameters = self.tx('Parámetros', 'Parameters')
        receives = self.tx('Recibe', 'Receives')
        kind = self.tx('Tipo', 'Type')
        complexity = self.tx('Complejidad', 'Complexity')

        parts = []
        if docstring:
            parts.append(f"<strong>{purpose}:</strong> {docstring}")
        else:
            detected = self.tx(
                f"Función <code>{name}</code> detectada en el proyecto.",
                f"Function <code>{name}</code> detected in the project.",
            )
            parts.append(f"<strong>{purpose}:</strong> {detected}")

        if params:
            param_list = ', '.join(f'<code>{p}</code>' for p in params if p != 'self')
            if param_list:
                parts.append(f"<strong>{parameters}:</strong> {receives} {param_list}.")

        if is_async:
            parts.append(
                f"<strong>{kind}:</strong> " + self.tx(
                    "Función asíncrona (<code>async/await</code>), diseñada para operaciones no bloqueantes.",
                    "Asynchronous function (<code>async/await</code>), designed for non-blocking operations.",
                )
            )

        if cx > 10:
            parts.append(f"<strong>{complexity}:</strong> " + self.tx(
                f"Alta ({cx}). Se recomienda refactorizar para mejorar la legibilidad.",
                f"High ({cx}). Refactoring is recommended to improve readability.",
            ))
        elif cx > 5:
            parts.append(f"<strong>{complexity}:</strong> " + self.tx(
                f"Moderada ({cx}). Contiene múltiples ramas de decisión.",
                f"Moderate ({cx}). It contains multiple decision branches.",
            ))

        return ' '.join(parts)

    def _api_section(self) -> str:
        eps = self.r.get("endpoints", [])
        title = self.t('code_docs_title')
        if not eps:
            return f"{title}\n\n{self.t('no_endpoints')}\n"

        out = f"{title}\n\n"

        # 3.1 Guía de configuración del entorno
        lang = self.r.get("primary_language", "Python")
        install_cmd = {
            "Python": "pip install -r requirements.txt",
            "JavaScript": "npm install",
            "TypeScript": "npm install",
        }.get(lang, self.tx("# instalar dependencias", "# install dependencies"))

        out += f"{self.t('env_setup')}\n\n"
        out += self.tx(f"""```bash
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

""", f"""```bash
# 1. Clone the repository
git clone <repository-url>
cd <project-name>

# 2. Create a virtual environment (recommended for Python)
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\\Scripts\\activate     # Windows

# 3. Install dependencies
{install_cmd}

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your local values

# 5. Run in development mode
python app.py  # or npm run dev
```

""")

        # 3.2 Tabla resumen de endpoints
        out += f"{self.t('endpoint_catalog')}\n\n"
        out += self.tx(
            f"El proyecto expone **{len(eps)} endpoints**. A continuación se presenta el catálogo completo organizado por módulo:\n\n",
            f"The project exposes **{len(eps)} endpoints**. The complete catalog organized by module is shown below:\n\n",
        )

        # Tabla resumen de todos los endpoints
        ep_rows = []
        for ep in eps:
            method = ep.get('method', 'GET')
            ep_rows.append([
                f"**{method}**",
                f"`{ep.get('path', '/')}`",
                f"`{ep.get('file', '?')}`",
                ep.get('framework', '—'),
            ])
        out += self._render_markdown_table(
            [self.t('method'), self.t('path'), self.t('file'), self.t('framework')],
            ep_rows
        )

        # Detalle por módulo
        by_file = {}
        for ep in eps:
            by_file.setdefault(ep.get("file", self.t('unknown')), []).append(ep)

        module_word = self.tx('Módulo', 'Module')
        for f, endpoints in by_file.items():
            out += f"\n#### {module_word}: `{f}`\n\n"
            for ep in endpoints:
                method = ep.get('method', 'GET')
                out += f"##### `{method} {ep.get('path')}`\n\n"
                # Cerrar bloques ``` abiertos si la IA se cortó a la mitad
                ai_desc = self._sanitize_ai_markdown(self._long_description(
                    'endpoint', ep, ep.get("ai_description") or ep.get("description") or ep.get("docstring")
                ))
                if ai_desc:
                    out += self._description_quote(ai_desc)

                # Tabla de detalle del endpoint
                detail_rows = [
                    ['Framework', ep.get('framework', self.t('unknown'))],
                    [self.t('file'), f"`{ep.get('file')}`"],
                ]
                if method in ('POST', 'PUT', 'PATCH'):
                    detail_rows.append(['Body', self.tx('JSON (requerido)', 'JSON (required)')])
                detail_rows.append(['Auth', 'Bearer JWT Token'])
                out += self._render_markdown_table([self.t('property'), self.t('value')], detail_rows)

                # Tabla de códigos de respuesta
                resp_rows = [
                    ['`200`', f"✅ {self.t('success_op')}"],
                    ['`400`', f"⚠️ {self.t('bad_request')}"],
                    ['`401`', f"🔒 {self.t('unauthorized')}"],
                    ['`404`', f"❌ {self.t('not_found')}"],
                    ['`500`', f"🔥 {self.t('server_error')}"],
                ]
                # Línea en blanco: sin ella esta tabla se fusiona con la de propiedades
                out += "\n" + self._render_markdown_table([self.t('code_col'), self.t('description')], resp_rows)
                out += "---\n\n"

        # 3.3 Estado de documentación
        fns = self.r.get("functions", [])
        documented = [f for f in fns if f.get("docstring")]
        undocumented = [f for f in fns if not f.get("docstring")]
        doc_pct = round(len(documented) / max(len(fns), 1) * 100)

        out += f"{self.t('doc_status')}\n\n"

        # Tabla de resumen de documentación
        doc_summary_rows = [
            [self.t('total_functions'), str(len(fns))],
            [f"✅ {self.t('documented')}", f"{len(documented)} ({doc_pct}%)"],
            [f"❌ {self.t('undocumented')}", f"{len(undocumented)} ({100 - doc_pct}%)"],
        ]
        out += self._render_markdown_table([self.t('metric'), self.t('value')], doc_summary_rows)

        documented_word = self.tx('documentado', 'documented')
        out += f"\n```text\n[{'█' * int(doc_pct/5)}{'░' * int((100-doc_pct)/5)}] {doc_pct}% {documented_word}\n```\n\n"

        # Fragmentos de código con docstrings como ejemplos
        if documented:
            out += f"{self.t('code_fragments')}\n\n"
            out += self.tx(
                "A continuación se muestran fragmentos reales del proyecto que cuentan con docstrings correctamente implementados:\n\n",
                "Below are real project fragments that have correctly implemented docstrings:\n\n",
            )
            for fn in documented[:4]:
                snippet = fn.get('code_snippet', '')
                if snippet:
                    explanation = self._generate_code_explanation(fn)
                    out += self._render_code_fragment(
                        fn['name'], fn.get('file', '?'), snippet, explanation,
                        self.r.get('primary_language', 'python').lower()
                    )
                else:
                    params_str = ", ".join(fn.get("params", []))
                    docstring = fn.get('docstring', '')
                    out += f"- **`{fn['name']}({params_str})`** — {docstring}\n"

        if undocumented:
            out += f"\n{self.t('need_docs')}\n\n"
            undoc_rows = []
            for fn in undocumented[:10]:
                params_str = ", ".join(fn.get("params", [])) or "—"
                undoc_rows.append([f"`{fn['name']}`", f"`{params_str}`", f"`{fn.get('file', '?')}`"])
            out += self._render_markdown_table(
                [self.t('function_col'), self.t('params_col'), self.t('file_col')], undoc_rows
            )
            if len(undocumented) > 10:
                out += self.tx(
                    f"\n_... y {len(undocumented) - 10} funciones más sin documentar._\n",
                    f"\n_... and {len(undocumented) - 10} more undocumented functions._\n",
                )
            out += "\n"

        # 3.4 Planes de Prueba (Testing) — EN TABLA
        test_fns = [f for f in fns if "test" in f["name"].lower() or f["name"].startswith("test_")]
        out += f"{self.t('test_plans')}\n\n"
        if test_fns:
            out += self.tx(
                f"Se detectaron **{len(test_fns)} funciones de prueba** en el proyecto:\n\n",
                f"**{len(test_fns)} test functions** were detected in the project:\n\n",
            )
            test_rows = []
            for fn in test_fns[:15]:
                cx = fn.get('complexity', 1)
                status = f'✅ {self.t("implemented")}'
                test_rows.append([
                    f"`{fn['name']}`",
                    f"`{fn.get('file', '?')}`",
                    f"{cx}",
                    status
                ])
            out += self._render_markdown_table(
                [self.t('test_function'), self.t('file'), self.t('complexity'), self.t('status')],
                test_rows
            )

            # Mostrar fragmentos de código de tests
            test_with_code = [f for f in test_fns if f.get('code_snippet')][:3]
            if test_with_code:
                out += self.tx("\n#### Fragmentos de Código de Tests\n\n", "\n#### Test Code Fragments\n\n")
                out += self.tx(
                    "Estos son fragmentos reales de las pruebas implementadas en el proyecto:\n\n",
                    "These are real fragments of the tests implemented in the project:\n\n",
                )
                for fn in test_with_code:
                    explanation = self._generate_code_explanation(fn)
                    out += self._render_code_fragment(
                        fn['name'], fn.get('file', '?'), fn['code_snippet'], explanation
                    )
        else:
            out += f"> ⚠️ {self.t('no_tests')}\n\n"
            out += self.tx(
                "Se recomienda implementar los siguientes escenarios de prueba:\n\n",
                "The following test scenarios are recommended:\n\n",
            )

            # Tabla profesional de escenarios recomendados
            scenario_rows = []
            for ep in eps[:8]:
                method = ep.get('method', 'GET')
                path = ep.get('path', '/')
                scenario_rows.append([
                    f"`{method} {path}`",
                    self.tx("Respuesta exitosa (200)", "Successful response (200)"),
                    self.tx("Integración", "Integration"),
                    self.tx("🔴 Alta", "🔴 High"),
                ])
                scenario_rows.append([
                    f"`{method} {path}`",
                    self.tx("Sin autenticación (401)", "Without authentication (401)"),
                    self.tx("Seguridad", "Security"),
                    self.tx("🔴 Alta", "🔴 High"),
                ])
                if method in ('POST', 'PUT', 'PATCH'):
                    scenario_rows.append([
                        f"`{method} {path}`",
                        self.tx("Datos inválidos (400)", "Invalid data (400)"),
                        self.tx("Validación", "Validation"),
                        self.tx("🟡 Media", "🟡 Medium"),
                    ])
            out += self._render_markdown_table(
                ['Endpoint', self.tx('Escenario', 'Scenario'), self.tx('Tipo', 'Type'), self.tx('Prioridad', 'Priority')],
                scenario_rows
            )

            out += self.tx(
                "\n**Ejemplo de implementación recomendada:**\n\n",
                "\n**Recommended implementation example:**\n\n",
            )
            out += self.tx(
                "Se recomienda crear una clase `TestEndpoints` con métodos de prueba para cada endpoint: "
                "verificar respuestas exitosas (200), creación de recursos (201), y acceso no autorizado (401). "
                "Utilizar un cliente de prueba (`client`) con `pytest` para ejecutar las pruebas de forma automatizada.\n\n",
                "It is recommended to create a `TestEndpoints` class with test methods for each endpoint: "
                "verify successful responses (200), resource creation (201), and unauthorized access (401). "
                "Use a test client (`client`) with `pytest` to run the tests automatically.\n\n",
            )

        return out

    # ─── 4. CLASES ────────────────────────────────────────────────────────────
    def _class_docs(self) -> list:
        docs = []
        for c in self.r.get("classes", []):
            # Usar descripción de IA si está disponible, sino usar docstring
            description = c.get("ai_description") or c.get("docstring") or self.tx(f"Clase {c['name']}", f"Class {c['name']}")
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
            return self.tx(
                "## 4. Clases\n\nNo se detectaron clases en este proyecto.\n",
                "## 4. Classes\n\nNo classes were detected in this project.\n",
            )

        out = self.tx(
            "## 4. Documentación de Clases y Módulos\n\n",
            "## 4. Class and Module Documentation\n\n",
        )
        out += self.tx(
            f"El proyecto contiene **{len(classes)} clases** distribuidas en los siguientes módulos.\n\n",
            f"The project contains **{len(classes)} classes** distributed across the following modules.\n\n",
        )

        # TABLA RESUMEN de todas las clases/módulos
        out += self.tx("### 4.1 Tabla Resumen de Módulos\n\n", "### 4.1 Module Summary Table\n\n")
        cls_rows = []
        for c in classes:
            methods_count = len(c.get('methods', []))
            bases = ', '.join(c.get('bases', [])) or 'object'
            doc_status = f'✅ {self.tx("Sí", "Yes")}' if c.get('docstring') else f'❌ {self.tx("No", "No")}'
            cls_rows.append([
                f"**`{c['name']}`**",
                f"`{c['file']}`",
                str(c.get('line', '—')),
                bases,
                str(methods_count),
                doc_status
            ])
        out += self._render_markdown_table(
            [self.tx('Clase', 'Class'), self.t('file'), self.tx('Línea', 'Line'), self.tx('Herencia', 'Inheritance'), self.t('method'), self.t('documented')],
            cls_rows
        )

        # Detalle de cada clase (clase + tablas juntos para evitar saltos de página)
        out += self.tx("\n### 4.2 Detalle de Clases\n\n", "\n### 4.2 Class Details\n\n")
        for c in classes:
            # El exportador mantiene juntos título + descripción + tabla (ver _keep_blocks_together)
            out += f"#### `{c['name']}`\n\n"
            # Cerrar bloques ``` abiertos si la IA se cortó a la mitad
            ai_desc = self._sanitize_ai_markdown(self._long_description(
                'class', c, c.get("ai_description") or c.get("description") or c.get("docstring")
            ))
            if ai_desc:
                out += self._description_quote(ai_desc)

            if c.get("methods"):
                method_rows = []
                for m in c["methods"][:20]:
                    method_rows.append([f"`{m}()`"])
                out += self._render_markdown_table([self.tx('Métodos disponibles', 'Available methods')], method_rows)

            out += '\n---\n\n'
        return out

    # ─── 5. FUNCIONES ─────────────────────────────────────────────────────────
    def _function_docs(self) -> list:
        docs = []
        for fn in self.r.get("functions", []):
            params_doc = [{"name": p, "type": "any", "description": self.tx(f"Parámetro {p}", f"Parameter {p}")}
                          for p in fn.get("params", [])]
            description = fn.get("ai_description") or fn.get("docstring") or self.tx(f"Función {fn['name']}", f"Function {fn['name']}")
            docs.append({
                "name":        fn["name"],
                "file":        fn["file"],
                "line":        fn.get("line"),
                "description": description,
                "parameters":  params_doc,
                "is_async":    fn.get("is_async", False),
                "complexity":  fn.get("complexity", 1),
                "lines_of_code": self._count_function_loc(fn),
                "returns":     {"type": "any", "description": self.tx("Valor de retorno", "Return value")},
            })
        return docs

    def _functions_section(self) -> str:
        fns = self.r.get("functions", [])
        if not fns:
            return self.tx(
                "## 5. Funciones\n\nNo se detectaron funciones.\n",
                "## 5. Functions\n\nNo functions were detected.\n",
            )

        # Agrupar por archivo
        by_file = {}
        for fn in fns:
            by_file.setdefault(fn.get("file", self.t('unknown')), []).append(fn)

        out = self.tx(
            f"## 5. Documentación de Funciones\n\nEl proyecto contiene **{len(fns)} funciones** distribuidas en **{len(by_file)} módulos**.\n\n",
            f"## 5. Function Documentation\n\nThe project contains **{len(fns)} functions** distributed across **{len(by_file)} modules**.\n\n",
        )

        # TABLA RESUMEN por módulo
        out += self.tx("### 5.1 Resumen por Módulo\n\n", "### 5.1 Module Summary\n\n")
        module_rows = []
        for fname, funcs in by_file.items():
            avg_cx = round(sum(f.get('complexity', 1) for f in funcs) / max(len(funcs), 1), 1)
            doc_count = sum(1 for f in funcs if f.get('docstring'))
            doc_pct = round(doc_count / max(len(funcs), 1) * 100)
            async_count = sum(1 for f in funcs if f.get('is_async'))
            module_rows.append([
                f"`{fname}`",
                str(len(funcs)),
                str(avg_cx),
                f"{doc_pct}%",
                str(async_count) if async_count else '—',
            ])
        out += self._render_markdown_table(
            [self.tx('Módulo', 'Module'), self.t('functions'), self.tx('Complejidad Prom.', 'Avg. complexity'), self.t('documented'), 'Async'],
            module_rows
        )

        # Detalle por módulo con tabla de funciones
        out += self.tx("\n### 5.2 Detalle por Módulo\n\n", "\n### 5.2 Module Details\n\n")
        module_word = self.tx('Módulo', 'Module')
        for fname, funcs in by_file.items():
            out += f"#### {module_word}: `{fname}`\n\n"

            # Tabla de funciones del módulo (incluye líneas de código de cada función)
            fn_rows = []
            for fn in funcs:
                cx = fn.get('complexity', 1)
                cx_badge = 'LOW' if cx <= 5 else 'MEDIUM' if cx <= 10 else 'HIGH'
                params = ', '.join(fn.get('params', [])) or '—'
                async_tag = ' `[ASYNC]`' if fn.get('is_async') else ''
                doc_tag = '✅' if fn.get('docstring') else '❌'
                loc = self._count_function_loc(fn)
                loc_str = str(loc) if loc is not None else '—'
                fn_rows.append([
                    f"`{fn['name']}`{async_tag}",
                    f"`{params}`",
                    loc_str,
                    f"{cx_badge} ({cx})",
                    doc_tag
                ])
            out += self._render_markdown_table(
                [self.t('function_col'), self.t('params_col'), self.tx('Líneas en la función', 'Function lines'), self.t('complexity'), self.tx('Doc', 'Docs')],
                fn_rows
            )

            # Fragmentos de código relevantes (máximo 3 por módulo)
            important_fns = sorted(funcs, key=lambda f: f.get('complexity', 1), reverse=True)
            code_shown = 0
            for fn in important_fns:
                if code_shown >= 3:
                    break
                snippet = fn.get('code_snippet', '')
                if snippet:
                    explanation = self._generate_code_explanation(fn)
                    out += self._render_code_fragment(
                        fn['name'], fn.get('file', '?'), snippet, explanation,
                        self.r.get('primary_language', 'python').lower()
                    )
                    code_shown += 1

            out += "\n---\n\n"

        return out

    # ─── 6. MODELOS DE DATOS ──────────────────────────────────────────────────
    def _data_models(self) -> str:
        # 1. Obtener modelos desde self.r.get("models") y self.r.get("classes")
        models_list = list(self.r.get("models") or [])
        classes = self.r.get("classes", [])
        
        # Combinar clases marcadas como modelo o que coincidan con nombres de modelo
        existing_keys = {(m.get("name"), m.get("file")) for m in models_list}
        for c in classes:
            key = (c.get("name"), c.get("file"))
            if key not in existing_keys:
                is_model = c.get("is_model") or any(
                    kw in c["name"].lower() for kw in ["model", "schema", "entity", "dto", "dao"]
                ) or any("model" in str(b).lower() or "base" in str(b).lower() for b in c.get("bases", []))
                if is_model:
                    models_list.append(c)
                    existing_keys.add(key)

        out = self.tx("## 6. Modelos de Datos\n\n", "## 6. Data Models\n\n")

        if models_list:
            out += self.tx(
                f"Se detectaron **{len(models_list)} modelos de datos**:\n\n",
                f"**{len(models_list)} data models** were detected:\n\n",
            )

            # Diagrama PlantUML de modelos
            models_puml = "@startuml\n"
            models_puml += "skinparam classAttributeIconSize 0\n"
            models_puml += "skinparam backgroundColor #FFFFFF\n"
            models_puml += "hide circle\n"
            for idx, m in enumerate(models_list[:12], start=1):
                safe_alias = f"model_{idx}"
                models_puml += f'class "{m.get("name", "Model")}" as {safe_alias} <<Entity>> {{\n'
                fields = m.get("fields", [])
                for fld in fields[:8]:
                    clean_fld = re.sub(r'[^a-zA-Z0-9_]', '', str(fld))
                    if clean_fld:
                        models_puml += f'  +{clean_fld}\n'
                methods = m.get("methods", [])
                if methods:
                    models_puml += '  --\n'
                    for met in methods[:4]:
                        clean_met = re.sub(r'[^a-zA-Z0-9_]', '', str(met))
                        if clean_met:
                            models_puml += f'  +{clean_met}()\n'
                models_puml += '}\n'
            models_puml += "@enduml"

            models_diagram = self._render_diagram_block(
                self.tx("Diagrama de Modelos de Datos", "Data Models Diagram"),
                models_puml
            )
            out += models_diagram

            # Tabla resumen de modelos
            out += self.tx("### 6.1 Tabla Resumen de Modelos\n\n", "### 6.1 Models Summary Table\n\n")
            model_rows = []
            for m in models_list:
                fields_str = ', '.join(f"`{f}`" for f in m.get("fields", [])[:5]) or "—"
                if len(m.get("fields", [])) > 5:
                    fields_str += f" ({len(m.get('fields', [])) - 5} {self.tx('más', 'more')})"
                methods_str = ', '.join(f"`{met}()`" for met in m.get("methods", [])[:3]) or "—"
                bases = ', '.join(m.get("bases", [])) or "object"
                model_rows.append([
                    f"**`{m['name']}`**",
                    f"`{m.get('file', '?')}`",
                    str(m.get('line', '—')),
                    bases,
                    fields_str,
                    methods_str,
                ])
            out += self._render_markdown_table(
                [self.tx('Modelo', 'Model'), self.t('file'), self.tx('Línea', 'Line'), self.tx('Herencia', 'Inheritance'), self.tx('Campos', 'Fields'), self.t('method')],
                model_rows
            )

            # Detalle de cada modelo (modelo + tablas juntos para evitar saltos de página)
            out += self.tx("\n### 6.2 Detalle de Modelos\n\n", "\n### 6.2 Model Details\n\n")
            for m in models_list:
                # El exportador mantiene juntos título + descripción + tabla (ver _keep_blocks_together)
                out += f"#### `{m['name']}`\n\n"
                desc = self._sanitize_ai_markdown(self._long_description(
                    'model', m, m.get("ai_description") or m.get("description") or m.get("docstring")
                ))
                if desc:
                    out += self._description_quote(desc)

                detail_rows = [
                    [self.t('file'), f"`{m.get('file', '?')}`"],
                    [self.tx('Línea', 'Line'), str(m.get('line', '—'))],
                    [self.tx('Hereda de', 'Inherits from'), f"`{', '.join(m.get('bases', [])) or 'object'}`"],
                ]
                out += self._render_markdown_table([self.t('property'), self.t('value')], detail_rows)

                # Tabla de campos si existen
                if m.get("fields"):
                    fld_rows = []
                    for fld in m["fields"]:
                        fld_name = fld if isinstance(fld, str) else fld.get("name", str(fld))
                        fld_type = fld.get("type", "Column") if isinstance(fld, dict) else "Attribute"
                        fld_rows.append([f"`{fld_name}`", f"`{fld_type}`"])
                    out += f"\n**{self.tx('Atributos / Columnas del Modelo', 'Model Attributes / Columns')}:**\n\n"
                    out += self._render_markdown_table([self.tx('Campo', 'Field'), self.tx('Tipo', 'Type')], fld_rows)

                # Métodos del modelo si existen
                if m.get("methods"):
                    method_rows = [[f"`{met}()`"] for met in m["methods"][:15]]
                    out += f"\n**{self.tx('Métodos del Modelo', 'Model Methods')}:**\n\n"
                    out += self._render_markdown_table([self.tx('Métodos disponibles', 'Available methods')], method_rows)

                out += '\n---\n\n'
        else:
            out += self.tx(
                "No se detectaron clases con nombres de modelo explícitos.\n\n",
                "No classes with explicit model names were detected.\n\n",
            )
            out += self.tx("### Esquema General Inferido\n\n", "### Inferred General Schema\n\n")
            out += self.tx(
                "Basado en el análisis del código, las entidades principales son:\n\n",
                "Based on the code analysis, the main entities are:\n\n",
            )
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
                out += self.tx(
                    "- No se pudieron inferir entidades del código fuente.\n",
                    "- No entities could be inferred from the source code.\n",
                )

        return out + "\n"

    def _generate_star_schema(self) -> str:
        """
        A partir de las clases tipo Model/Schema detectadas,
        genera un diagrama estrella de Data Warehouse en PlantUML.
        """
        classes = self.r.get("classes", [])
        model_classes = [c for c in classes if any(
            kw in c["name"].lower() for kw in ["model", "schema", "entity", "dto", "dao"]
        )]

        if not model_classes:
            return ""

        # Identificar tabla de hechos (clases con más métodos o relaciones)
        fact_table = None
        dimension_tables = []

        for cls in model_classes:
            methods = cls.get("methods", [])
            # Si tiene métodos CRUD, es probablemente una tabla de hechos
            if any(m in methods for m in ["create", "update", "delete", "save"]):
                if not fact_table:
                    fact_table = cls
                else:
                    dimension_tables.append(cls)
            else:
                dimension_tables.append(cls)

        # Si no se encontró tabla de hechos, usar la primera como tabla de hechos
        if not fact_table and model_classes:
            fact_table = model_classes[0]
            dimension_tables = model_classes[1:]

        # Generar diagrama PlantUML estrella
        puml = "@startuml\n"
        puml += "skinparam backgroundColor #FEFEFE\n"
        puml += f"title {self.tx('Diagrama Estrella de Data Warehouse', 'Data Warehouse Star Schema')}\n\n"

        # Tabla de hechos
        if fact_table:
            puml += f"class \"{fact_table['name']}\" as fact <<FactTable>> {{\n"
            for method in fact_table.get("methods", [])[:5]:
                clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(method))
                if clean_m:
                    puml += f"  +{clean_m}()\n"
            puml += "}\n\n"

        # Tablas de dimensión
        for idx, dim in enumerate(dimension_tables[:8], start=1):
            dim_alias = f"dim_{idx}"
            puml += f"class \"{dim['name']}\" as {dim_alias} <<Dimension>> {{\n"
            for method in dim.get("methods", [])[:3]:
                clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(method))
                if clean_m:
                    puml += f"  +{clean_m}()\n"
            puml += "}\n\n"

        # Relaciones
        if fact_table:
            for idx in range(1, len(dimension_tables[:8]) + 1):
                puml += f"dim_{idx} --> fact : FK\n"

        puml += "@enduml"

        # Generar imagen
        return self._render_diagram_block(self.tx('Diagrama Estrella de Data Warehouse', 'Data Warehouse Star Schema'), puml)

    def _generate_snowflake_schema(self) -> str:
        """
        Genera un diagrama copo de nieve (snowflake) de Data Warehouse en PlantUML.
        """
        classes = self.r.get("classes", [])
        model_classes = [c for c in classes if any(
            kw in c["name"].lower() for kw in ["model", "schema", "entity", "dto", "dao"]
        )]

        if len(model_classes) < 3:
            return ""

        # Generar diagrama PlantUML copo de nieve
        puml = "@startuml\n"
        puml += "skinparam backgroundColor #FEFEFE\n"
        puml += f"title {self.tx('Diagrama Copo de Nieve de Data Warehouse', 'Data Warehouse Snowflake Schema')}\n\n"

        # Tabla central (hechos)
        central = model_classes[0]
        puml += f"class \"{central['name']}\" as central <<FactTable>> {{\n"
        for method in central.get("methods", [])[:3]:
            clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(method))
            if clean_m:
                puml += f"  +{clean_m}()\n"
        puml += "}\n\n"

        # Dimensiones primarias
        for i, dim in enumerate(model_classes[1:5]):
            puml += f"class \"{dim['name']}\" as dim{i} <<Dimension>> {{\n"
            for method in dim.get("methods", [])[:2]:
                clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(method))
                if clean_m:
                    puml += f"  +{clean_m}()\n"
            puml += "}\n\n"
            puml += f"dim{i} --> central : FK\n\n"

        # Sub-dimensiones (copo de nieve)
        for i, dim in enumerate(model_classes[5:8]):
            parent_dim = i % 4  # Ciclar entre dimensiones primarias
            puml += f"class \"{dim['name']}\" as subdim{i} <<SubDimension>> {{\n"
            for method in dim.get("methods", [])[:2]:
                clean_m = re.sub(r'[^a-zA-Z0-9_]', '', str(method))
                if clean_m:
                    puml += f"  +{clean_m}()\n"
            puml += "}\n\n"
            puml += f"subdim{i} --> dim{parent_dim} : FK\n\n"

        puml += "@enduml"

        # Generar imagen
        return self._render_diagram_block(self.tx('Diagrama Copo de Nieve de Data Warehouse', 'Data Warehouse Snowflake Schema'), puml)

    def _data_analysis_section(self) -> str:
        """
        Genera la Sección 9: Análisis de Datos del Proyecto.

        Incluye:
        - Esquema de Data Warehouse inferido (estrella/copo de nieve)
        - Tipos y fuentes de datos detectados en el repositorio
        - Reporte de limpieza de datos
        - Diagrama del pipeline ETL
        """
        out = self.tx("## 9. Análisis de Datos del Proyecto\n\n", "## 9. Project Data Analysis\n\n")

        # 9.1 Tipos y fuentes de datos detectados
        data_types = self.r.get("data_types", {"structured": [], "semi_structured": [], "unstructured": []})
        structured = data_types.get("structured", [])
        semi_structured = data_types.get("semi_structured", [])
        unstructured = data_types.get("unstructured", [])
        files_word = self.tx("archivos", "files")
        more_word = self.tx("más", "more")

        out += self.tx("### 9.1 Tipos y Fuentes de Datos Detectados\n\n", "### 9.1 Detected Data Types and Sources\n\n")
        out += self.tx(
            f"**Datos Estructurados:** {len(structured)} archivos\n",
            f"**Structured data:** {len(structured)} files\n",
        )
        if structured:
            for file in structured[:10]:
                out += f"- `{file}`\n"
            if len(structured) > 10:
                out += f"- ... {len(structured) - 10} {more_word}\n"

        out += self.tx(
            f"\n**Datos Semi-estructurados:** {len(semi_structured)} archivos\n",
            f"\n**Semi-structured data:** {len(semi_structured)} files\n",
        )
        if semi_structured:
            for file in semi_structured[:10]:
                out += f"- `{file}`\n"
            if len(semi_structured) > 10:
                out += f"- ... {len(semi_structured) - 10} {more_word}\n"

        out += self.tx(
            f"\n**Datos No Estructurados:** {len(unstructured)} archivos\n",
            f"\n**Unstructured data:** {len(unstructured)} files\n",
        )
        if unstructured:
            for file in unstructured[:10]:
                out += f"- `{file}`\n"
            if len(unstructured) > 10:
                out += f"- ... {len(unstructured) - 10} {more_word}\n"

        # 9.2 Esquema de Data Warehouse inferido
        out += self.tx("\n### 9.2 Esquema de Data Warehouse Inferido\n\n", "\n### 9.2 Inferred Data Warehouse Schema\n\n")
        star_schema = self._generate_star_schema()
        snowflake_schema = self._generate_snowflake_schema()

        if star_schema:
            out += self.tx("**Diagrama Estrella (Star Schema):**\n\n", "**Star Schema Diagram:**\n\n")
            out += star_schema
            out += self.tx(
                "\nEl esquema estrella es adecuado para consultas analíticas rápidas, con una tabla de hechos central conectada a tablas de dimensión.\n\n",
                "\nThe star schema is suitable for fast analytical queries, with a central fact table connected to dimension tables.\n\n",
            )
        elif snowflake_schema:
            out += self.tx("**Diagrama Copo de Nieve (Snowflake Schema):**\n\n", "**Snowflake Schema Diagram:**\n\n")
            out += snowflake_schema
            out += self.tx(
                "\nEl esquema copo de nieve normaliza las dimensiones para reducir redundancia, a costa de consultas más complejas.\n\n",
                "\nThe snowflake schema normalizes dimensions to reduce redundancy, at the cost of more complex queries.\n\n",
            )
        else:
            out += self.tx(
                "No se detectaron suficientes modelos de datos para generar un esquema de Data Warehouse.\n\n",
                "Not enough data models were detected to generate a data warehouse schema.\n\n",
            )

        # 9.3 Reporte de calidad de datos
        out += self.tx("### 9.3 Reporte de Calidad de Datos\n\n", "### 9.3 Data Quality Report\n\n")

        # Aplicar limpieza de datos al análisis
        from services.data_cleaner import DataCleaner
        cleaner = DataCleaner()

        # Detectar problemas en el código
        code_issues = cleaner.clean_code_issues(self.r)

        out += self.tx("**Problemas Detectados en el Código:**\n\n", "**Issues Detected in the Code:**\n\n")
        in_word = self.tx("en", "in")
        more_word = self.tx("más", "more")

        if code_issues.get("missing_docstrings"):
            out += self.tx(
                f"- **Funciones sin documentar:** {len(code_issues['missing_docstrings'])}\n",
                f"- **Undocumented functions:** {len(code_issues['missing_docstrings'])}\n",
            )
            for issue in code_issues["missing_docstrings"][:5]:
                out += f"  - `{issue['name']}` {in_word} `{issue['file']}`\n"
            if len(code_issues["missing_docstrings"]) > 5:
                out += f"  - ... {len(code_issues['missing_docstrings']) - 5} {more_word}\n"

        if code_issues.get("high_complexity"):
            out += self.tx(
                f"\n- **Funciones de alta complejidad:** {len(code_issues['high_complexity'])}\n",
                f"\n- **High-complexity functions:** {len(code_issues['high_complexity'])}\n",
            )
            for issue in code_issues["high_complexity"][:5]:
                complexity_label = self.tx("complejidad", "complexity")
                out += f"  - `{issue['name']}` {in_word} `{issue['file']}` ({complexity_label}: {issue['complexity']})\n"
            if len(code_issues["high_complexity"]) > 5:
                out += f"  - ... {len(code_issues['high_complexity']) - 5} {more_word}\n"

        if code_issues.get("naming_conventions"):
            out += self.tx(
                f"\n- **Problemas de naming conventions:** {len(code_issues['naming_conventions'])}\n",
                f"\n- **Naming convention issues:** {len(code_issues['naming_conventions'])}\n",
            )
            for issue in code_issues["naming_conventions"][:5]:
                out += f"  - `{issue['name']}`: {issue['message']}\n"

        # 9.4 Minería de datos aplicada al código
        out += self.tx(
            "\n### 9.4 Minería de Datos Aplicada al Código\n\n",
            "\n### 9.4 Data Mining Applied to the Code\n\n",
        )
        out += self.tx(
            "_Análisis automático realizado sobre las funciones y clases extraídas del proyecto._\n\n",
            "_Automatic analysis performed on the functions and classes extracted from the project._\n\n",
        )

        fns_mining  = self.r.get("functions", [])
        cls_mining  = self.r.get("classes", [])

        # ── A) Funciones de alta complejidad ──────────────────────────────────
        out += self.tx(
            "#### A) Funciones de Alta Complejidad Ciclomática\n\n",
            "#### A) Functions with High Cyclomatic Complexity\n\n",
        )
        high_cx = sorted(
            [f for f in fns_mining if f.get("complexity", 1) > 5],
            key=lambda f: f.get("complexity", 1),
            reverse=True
        )
        medium_cx = [f for f in fns_mining if 3 < f.get("complexity", 1) <= 5]
        low_cx    = [f for f in fns_mining if f.get("complexity", 1) <= 3]

        out += f"| {self.tx('Nivel', 'Level')} | {self.tx('Umbral', 'Threshold')} | {self.tx('Cantidad', 'Count')} | {self.t('description')} |\n"
        out += "|---|---|---|---|\n"
        out += f"| 🔴 {self.tx('Alta', 'High')} | > 5 | {len(high_cx)} | {self.tx('Requieren refactorización urgente', 'Require urgent refactoring')} |\n"
        out += f"| 🟡 {self.tx('Media', 'Medium')} | 4–5 | {len(medium_cx)} | {self.tx('Candidatas a simplificación', 'Candidates for simplification')} |\n"
        out += f"| 🟢 {self.tx('Baja', 'Low')} | ≤ 3 | {len(low_cx)} | {self.tx('Complejidad aceptable', 'Acceptable complexity')} |\n\n"

        if high_cx:
            out += self.tx(
                "**Funciones de alta complejidad — detalle y recomendaciones:**\n\n",
                "**High-complexity functions — details and recommendations:**\n\n",
            )
            for fn in high_cx[:15]:
                cx    = fn.get("complexity", 1)
                name  = fn.get("name", "?")
                file  = fn.get("file", "?")
                line  = fn.get("line", "?")
                async_tag = " `[async]`" if fn.get("is_async") else ""
                doc_tag   = f" `[{self.tx('sin docstring', 'no docstring')}]`" if not fn.get("docstring") else ""
                out += f"- **`{name}`**{async_tag}{doc_tag}\n"
                out += f"  - 📁 {self.t('file')}: `{file}` — {self.tx('línea', 'line')} {line}\n"
                out += f"  - 📊 {self.tx('Complejidad ciclomática', 'Cyclomatic complexity')}: **{cx}**\n"
                suggestion = self.tx("Sugerencia", "Suggestion")
                if cx > 15:
                    out += self.tx(
                        f"  - 💡 {suggestion}: Complejidad crítica ({cx}). Divide esta función en al menos {cx // 5} funciones más pequeñas con responsabilidad única. Cada rama lógica (if/for/while) debería ser su propio método.\n",
                        f"  - 💡 {suggestion}: Critical complexity ({cx}). Split this function into at least {cx // 5} smaller functions with a single responsibility. Each logical branch (if/for/while) should be its own method.\n",
                    )
                elif cx > 10:
                    out += self.tx(
                        f"  - 💡 {suggestion}: Complejidad alta ({cx}). Extrae las ramas condicionales a funciones auxiliares privadas y considera el patrón de «guardas tempranas» (early return) para reducir el anidamiento.\n",
                        f"  - 💡 {suggestion}: High complexity ({cx}). Extract conditional branches into private helper functions and consider the early-return guard pattern to reduce nesting.\n",
                    )
                else:
                    out += self.tx(
                        f"  - 💡 {suggestion}: Complejidad moderada-alta ({cx}). Revisa si alguno de los bloques if/for puede extraerse a una función con nombre descriptivo.\n",
                        f"  - 💡 {suggestion}: Moderate-to-high complexity ({cx}). Check whether any if/for block can be extracted into a descriptively named function.\n",
                    )
                out += "\n"
        else:
            out += self.tx(
                "> ✅ No se detectaron funciones con complejidad ciclomática alta. El código mantiene un buen nivel de simplicidad.\n\n",
                "> ✅ No functions with high cyclomatic complexity were detected. The code maintains a good level of simplicity.\n\n",
            )

        # ── B) Funciones sin documentar ────────────────────────────────────────
        out += self.tx("#### B) Funciones Sin Documentación\n\n", "#### B) Undocumented Functions\n\n")
        undoc = [f for f in fns_mining if not f.get("docstring")]
        doc   = [f for f in fns_mining if f.get("docstring")]
        doc_pct = round(len(doc) / max(len(fns_mining), 1) * 100)

        out += self.tx(
            f"**{len(undoc)} de {len(fns_mining)} funciones** carecen de docstring ({100 - doc_pct}%).\n\n",
            f"**{len(undoc)} of {len(fns_mining)} functions** lack a docstring ({100 - doc_pct}%).\n\n",
        )
        if undoc:
            out += f"| {self.t('function_col')} | {self.t('file')} | {self.tx('Línea', 'Line')} | {self.t('complexity')} |\n"
            out += "|---|---|---|---|\n"
            for fn in undoc[:20]:
                out += f"| `{fn.get('name','?')}` | `{fn.get('file','?')}` | {fn.get('line','?')} | {fn.get('complexity',1)} |\n"
            if len(undoc) > 20:
                out += self.tx(
                    f"\n_... y {len(undoc) - 20} funciones más sin documentar._\n",
                    f"\n_... and {len(undoc) - 20} more undocumented functions._\n",
                )
            out += self.tx(
                "\n💡 **Sugerencia:** Agrega docstrings a todas las funciones públicas. Prioriza las de mayor complejidad primero, ya que son las más difíciles de entender sin documentación.\n\n",
                "\n💡 **Suggestion:** Add docstrings to all public functions. Prioritize the most complex ones first, as they are the hardest to understand without documentation.\n\n",
            )

        # ── C) Detección de funciones similares (posibles duplicados) ──────────
        out += self.tx(
            "#### C) Detección de Funciones con Nombres Similares (Posibles Duplicados)\n\n",
            "#### C) Detection of Similarly Named Functions (Possible Duplicates)\n\n",
        )
        out += self.tx(
            "_Se comparan los nombres de funciones entre archivos para detectar lógica duplicada o que podría unificarse._\n\n",
            "_Function names are compared across files to detect duplicated or unifiable logic._\n\n",
        )

        # Agrupar funciones por nombre base (quitar prefijos comunes)
        from collections import defaultdict
        import re as _re

        name_groups = defaultdict(list)
        for fn in fns_mining:
            raw_name = fn.get("name", "")
            # Normalizar: quitar prefijos de módulo típicos (get_, set_, create_, update_, delete_, handle_, _)
            base = _re.sub(
                r'^(get_|set_|create_|update_|delete_|handle_|fetch_|save_|load_|build_|make_|check_|validate_|process_|send_|render_|init_|setup_|on_|_)+',
                '', raw_name.lower()
            )
            # También agrupar si el nombre termina igual tras quitar prefijo de módulo
            # por ejemplo user_edit y admin_edit → ambos tienen "edit" como raíz
            # Tomamos los últimos 2 tokens del nombre separados por _
            parts = raw_name.lower().split("_")
            suffix_key = "_".join(parts[-2:]) if len(parts) >= 2 else raw_name.lower()
            name_groups[suffix_key].append(fn)

        # Filtrar solo grupos con 2+ funciones en archivos distintos, excluyendo nombres genéricos
        generic_names = {
            "__init__", "__str__", "__repr__", "__eq__", "__hash__", "index",
            "get", "set", "run", "main", "test", "setup", "teardown", "helper",
            "handle", "handler", "create", "update", "delete", "save", "load",
        }
        duplicates_found = []
        for suffix, group in name_groups.items():
            if suffix in generic_names or len(suffix) <= 2:
                continue
            files_in_group = list({fn.get("file", "") for fn in group})
            if len(files_in_group) >= 2:
                duplicates_found.append((suffix, group, files_in_group))

        # Ordenar por cantidad de archivos afectados (mayor primero)
        duplicates_found.sort(key=lambda x: len(x[2]), reverse=True)

        if duplicates_found:
            out += self.tx(
                f"Se detectaron **{len(duplicates_found)} grupos de funciones con nombres similares** repartidas en distintos archivos:\n\n",
                f"**{len(duplicates_found)} groups of similarly named functions** were detected across different files:\n\n",
            )
            for suffix, group, files_in_group in duplicates_found[:20]:
                appears_in = self.tx("aparece en", "appears in")
                distinct_files = self.tx("archivos distintos", "different files")
                out += f"**{self.tx('Patrón', 'Pattern')}: `*_{suffix}` / `{suffix}_*`** — {appears_in} {len(files_in_group)} {distinct_files}\n\n"
                out += f"| {self.t('function_col')} | {self.t('file')} | {self.tx('Línea', 'Line')} | {self.t('complexity')} |\n"
                out += "|---|---|---|---|\n"
                for fn in group:
                    out += f"| `{fn.get('name','?')}` | `{fn.get('file','?')}` | {fn.get('line','?')} | {fn.get('complexity',1)} |\n"

                # Generar sugerencia específica con los nombres reales
                fn_names = [f"`{fn.get('name','?')}`" for fn in group]
                fn_files = list({fn.get('file','?') for fn in group})
                suggestion = self.tx("Sugerencia", "Suggestion")
                if len(fn_names) == 2:
                    out += self.tx(
                        f"\n💡 **{suggestion}:** Las funciones {fn_names[0]} y {fn_names[1]} realizan operaciones similares (`{suffix}`) en módulos distintos. ",
                        f"\n💡 **{suggestion}:** Functions {fn_names[0]} and {fn_names[1]} perform similar operations (`{suffix}`) in different modules. ",
                    )
                    out += self.tx(
                        f"Considera crear una función compartida en un módulo utilitario (por ejemplo `utils/{suffix}.py` o `helpers/common.py`) ",
                        f"Consider creating a shared function in a utility module (for example `utils/{suffix}.py` or `helpers/common.py`) ",
                    )
                    out += self.tx(
                        f"que reciba el contexto como parámetro, y llamarla desde ambos archivos ({', '.join([f'`{f}`' for f in fn_files])}).\n\n",
                        f"that receives the context as a parameter and call it from both files ({', '.join([f'`{f}`' for f in fn_files])}).\n\n",
                    )
                else:
                    out += self.tx(
                        f"\n💡 **{suggestion}:** Las {len(fn_names)} funciones {', '.join(fn_names[:4])}{'...' if len(fn_names) > 4 else ''} comparten el patrón `{suffix}` en distintos módulos. ",
                        f"\n💡 **{suggestion}:** The {len(fn_names)} functions {', '.join(fn_names[:4])}{'...' if len(fn_names) > 4 else ''} share the `{suffix}` pattern across different modules. ",
                    )
                    out += self.tx(
                        "Esto sugiere lógica duplicada. Extrae la lógica común a un servicio o función base y haz que cada módulo la llame con sus parámetros propios.\n\n",
                        "This suggests duplicated logic. Extract the common logic into a shared service or base function and have each module call it with its own parameters.\n\n",
                    )
                out += "---\n\n"
        else:
            out += self.tx(
                "> ✅ No se detectaron funciones con nombres similares en archivos distintos.\n\n",
                "> ✅ No similarly named functions were detected across different files.\n\n",
            )

        # ── D) Clustering por archivo (módulos sobrecargados) ──────────────────
        out += self.tx(
            "#### D) Análisis de Módulos — Archivos con Mayor Concentración de Funciones\n\n",
            "#### D) Module Analysis — Files with the Highest Concentration of Functions\n\n",
        )
        file_fn_count = defaultdict(list)
        for fn in fns_mining:
            file_fn_count[fn.get("file", "?")].append(fn)

        sorted_files = sorted(file_fn_count.items(), key=lambda x: len(x[1]), reverse=True)
        out += f"| {self.t('file')} | {self.t('functions')} | {self.tx('Complejidad Promedio', 'Average Complexity')} | {self.t('documented')} | {self.t('status')} |\n"
        out += "|---|---|---|---|---|\n"
        for fname, funcs in sorted_files[:15]:
            avg_cx   = round(sum(f.get("complexity", 1) for f in funcs) / max(len(funcs), 1), 1)
            doc_cnt  = sum(1 for f in funcs if f.get("docstring"))
            doc_pct_f = round(doc_cnt / max(len(funcs), 1) * 100)
            if len(funcs) > 20 or avg_cx > 8:
                status = f"🔴 {self.tx('Sobrecargado', 'Overloaded')}"
            elif len(funcs) > 10 or avg_cx > 5:
                status = f"🟡 {self.tx('Revisar', 'Review')}"
            else:
                status = "🟢 OK"
            out += f"| `{fname}` | {len(funcs)} | {avg_cx} | {doc_pct_f}% | {status} |\n"

        out += "\n"
        for fname, funcs in sorted_files[:5]:
            if len(funcs) > 10:
                out += self.tx(
                    f"💡 **`{fname}`** tiene {len(funcs)} funciones. ",
                    f"💡 **`{fname}`** has {len(funcs)} functions. ",
                )
                out += self.tx(
                    "Considera dividirlo en submódulos más específicos siguiendo el principio de responsabilidad única (SRP).\n",
                    "Consider splitting it into more specific submodules following the single responsibility principle (SRP).\n",
                )
        out += "\n"

        # ── E) Patrones de código detectados (mining_results externo si existe) ─
        mining_results = self.r.get("mining_results", {})
        if mining_results:
            frequent_patterns = mining_results.get("frequent_patterns", [])
            if frequent_patterns:
                out += self.tx(
                    "#### E) Patrones Frecuentes Adicionales (Análisis IA)\n\n",
                    "#### E) Additional Frequent Patterns (AI Analysis)\n\n",
                )
                for pattern in frequent_patterns:
                    occurrences = self.tx("ocurrencias", "occurrences")
                    out += f"- **{pattern.get('pattern', 'N/A')}**: {pattern.get('frequency', 0)} {occurrences}"
                    if pattern.get('file'):
                        out += f" — 📁 `{pattern['file']}`"
                        if pattern.get('line'):
                            out += f" {self.tx('línea', 'line')} {pattern['line']}"
                    out += "\n"
                    if pattern.get('examples'):
                        out += f"  - {self.tx('Ejemplos', 'Examples')}: {pattern['examples']}\n"
                out += "\n"

        # 9.5 Diagrama del Pipeline ETL
        out += self.tx("### 9.5 Pipeline ETL Utilizado\n\n", "### 9.5 ETL Pipeline Used\n\n")
        out += self.tx(
            "El proceso de generación de documentación sigue un pipeline ETL (Extract, Transform, Load):\n\n",
            "The documentation generation process follows an ETL pipeline (Extract, Transform, Load):\n\n",
        )

        pipeline_cls = ETLPipeline
        if pipeline_cls is None:
            from services.etl_pipeline import ETLPipeline as pipeline_cls
        pipeline = pipeline_cls()
        etl_diagram = pipeline.get_pipeline_diagram()

        # Generar imagen del diagrama ETL
        etl_image = self._render_diagram_block(self.tx('Diagrama del Pipeline ETL', 'ETL Pipeline Diagram'), etl_diagram)
        out += etl_image

        out += self.tx("\n**Fases del Pipeline:**\n\n", "\n**Pipeline Stages:**\n\n")
        out += self.tx(
            "- **Extract:** Extracción de código desde repositorios GitHub, archivos ZIP o directorios locales\n",
            "- **Extract:** Code extraction from GitHub repositories, ZIP files or local directories\n",
        )
        out += self.tx(
            "- **Transform:** Análisis del código, limpieza de datos, enriquecimiento con IA y minería de patrones\n",
            "- **Transform:** Code analysis, data cleaning, AI enrichment and pattern mining\n",
        )
        out += self.tx(
            "- **Load:** Generación de documentación en HTML, PDF o almacenamiento en MongoDB\n\n",
            "- **Load:** Documentation generation in HTML/PDF or storage in MongoDB\n\n",
        )

        return out

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
        }.get(lang, "# install dependencies" if self.lang == 'en' else "# instalar dependencias")

        run_cmd = {
            "Python":     "python app.py",
            "JavaScript": "npm start",
            "TypeScript": "npm run build && npm start",
            "Java":       "mvn spring-boot:run",
            "Go":         "go run main.go",
        }.get(lang, "# run project" if self.lang == 'en' else "# ejecutar proyecto")

        if self.lang == 'en':
            return f"""## 7. Deployment and Maintenance Guide

### 7.1 System Requirements

- **Primary language**: {lang}
- **Detected files**: {self.r.get('total_files', 0)}

### 7.2 Local Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd <project-name>

# 2. Install dependencies
{install_cmd}

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your values

# 4. Run the project
{run_cmd}
```

### 7.3 Docker Deployment

```dockerfile
FROM {self._get_docker_base(lang)}

WORKDIR /app
COPY . .
RUN {install_cmd}
EXPOSE 8000
CMD ["{self._get_docker_cmd(lang)}"]
```

```bash
# Build image
docker build -t my-project .

# Run container
docker run -p 8000:8000 my-project
```

### 7.4 Recommended Environment Variables

```env
# General
APP_ENV=production
SECRET_KEY=secure-secret-key
DEBUG=False

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=my_database
DB_USER=user
DB_PASSWORD=password

# API
API_VERSION=v1
ALLOWED_HOSTS=*
```

### 7.5 Deployment Checklist

- [ ] Environment variables configured
- [ ] Database migrated
- [ ] Tests executed and passing
- [ ] Logs configured
- [ ] HTTPS enabled in production
- [ ] Backups scheduled
- [ ] Monitoring configured

### 7.6 Changelog

**Version 1.0.0** — {datetime.utcnow().strftime('%Y-%m-%d')}
- Initial version analyzed by AutoDocs AI
- Technical documentation generated automatically
- Code quality analysis completed

"""
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

        # Etiqueta de calidad con color (sin emojis)
        if score >= 80:
            quality_text, quality_color = (self.t('excellent'), "#16a34a")
        elif score >= 60:
            quality_text, quality_color = (('Good' if self.lang == 'en' else 'Bueno'), "#d97706")
        else:
            quality_text, quality_color = (('Needs improvement' if self.lang == 'en' else 'Necesita mejoras'), "#dc2626")

        recommendations = []
        if doc_pct < 50:
            recommendations.append(
                f"- Add docstrings to the {len(fns) - documented_fns} undocumented functions" if self.lang == 'en'
                else f"- Agregar docstrings a las {len(fns) - documented_fns} funciones sin documentar"
            )
        if high_cx_fns:
            names = ", ".join(f"`{f['name']}`" for f in high_cx_fns[:5])
            recommendations.append(
                f"- Refactor high-complexity functions: {names}" if self.lang == 'en'
                else f"- Refactorizar funciones con alta complejidad: {names}"
            )
        if issues:
            recommendations.append(
                f"- Resolve {len(issues)} detected analysis errors" if self.lang == 'en'
                else f"- Resolver {len(issues)} errores de análisis detectados"
            )
        if not recommendations:
            recommendations.append(
                "- The code has good overall quality. Keep up the good practices!" if self.lang == 'en'
                else "- El código tiene buena calidad general. ¡Mantén las buenas prácticas!"
            )

        trend = ("↑ Increasing" if cx.get('avg', 1) > 5 else "→ Stable" if cx.get('avg', 1) > 2 else "↓ Low") if self.lang == 'en' else ("↑ Aumentando" if cx.get('avg', 1) > 5 else "→ Estable" if cx.get('avg', 1) > 2 else "↓ Baja")
        no_high = "No functions with complexity > 10. [OK]" if self.lang == 'en' else "No hay funciones con complejidad > 10. [OK]"
        no_issues = "No issues detected. [OK]" if self.lang == 'en' else "Sin errores detectados. [OK]"
        in_word = 'in' if self.lang == 'en' else 'en'
        complexity_word = 'complexity' if self.lang == 'en' else 'complejidad'

        return f"""## 8. {('Code Quality Report' if self.lang == 'en' else 'Reporte de Calidad del Código')}

### 8.1 {('Metrics Analysis' if self.lang == 'en' else 'Análisis de Métricas')}

**{('Quality Score' if self.lang == 'en' else 'Score de Calidad')}:** {score}/100 — **{quality_text}**
{self._color_bar_html(quality_color, alt=('Quality level' if self.lang == 'en' else 'Nivel de calidad'))}

**{('Documentation Coverage' if self.lang == 'en' else 'Distribución de Documentación')}:**
- {('Documented functions' if self.lang == 'en' else 'Funciones documentadas')}: {documented_fns}/{len(fns)} ({doc_pct}%)
- {('Documented classes' if self.lang == 'en' else 'Clases documentadas')}: {documented_cls}/{len(cls)}

**{('Complexity Analysis' if self.lang == 'en' else 'Análisis de Complejidad')}:**
- {('Average complexity' if self.lang == 'en' else 'Complejidad promedio')}: {round(cx.get('avg', 1), 2)}
- {('Maximum complexity' if self.lang == 'en' else 'Complejidad máxima')}: {cx.get('max', 0)}
- {('High-complexity functions (>10)' if self.lang == 'en' else 'Funciones con alta complejidad (>10)')}: {len(high_cx_fns)}

**{('Complexity Trend by File' if self.lang == 'en' else 'Tendencia de Complejidad por Archivo')}:**
```text
[{'Linear regression chart showing complexity trend' if self.lang == 'en' else 'Gráfico de regresión lineal mostrando la tendencia de complejidad'}]
{'X-axis: Files ordered by average complexity' if self.lang == 'en' else 'Eje X: Archivos ordenados por complejidad promedio'}
{'Y-axis: Complexity score' if self.lang == 'en' else 'Eje Y: Score de complejidad'}
{'Trend' if self.lang == 'en' else 'Tendencia'}: {trend}
```

### 8.2 {('High Cyclomatic Complexity Functions' if self.lang == 'en' else 'Funciones con Alta Complejidad Ciclomática')}

{no_high if not high_cx_fns else chr(10).join(
    f"- `{f['name']}` {in_word} `{f['file']}` — {complexity_word}: **{f.get('complexity')}**"
    for f in high_cx_fns[:10]
)}

### 8.3 {('Recommendations' if self.lang == 'en' else 'Recomendaciones')}

{chr(10).join(recommendations)}

### 8.4 {('Analysis Issues' if self.lang == 'en' else 'Errores de Análisis')}

{no_issues if not issues else chr(10).join(
    f"- `{i.get('file', '?')}`: {i.get('error', '?')}"
    for i in issues[:10]
)}
"""

    # ─── MARKDOWN COMPLETO ────────────────────────────────────────────────────
    def _full_markdown(self, sections=None) -> str:
        if sections is None:
            sections = {
                "readme": self._readme(),
                "architecture": self._architecture(),
                "api_section": self._api_section(),
                "classes_section": self._classes_section(),
                "functions_section": self._functions_section(),
                "data_models": self._data_models(),
                "deployment": self._deployment(),
                "quality_report": self._quality_report(),
                "data_analysis": self._data_analysis_section(),
            }

        separator = "\n\n---\n\n"
        end_text = (
            f"\n\n---\n*AutoDocs AI · End of technical document · Analysis status: {self.now}*\n"
            if self.lang == 'en' else
            f"\n\n---\n*AutoDocs AI · Fin del documento técnico · Estado del análisis: {self.now}*\n"
        )
        return (
            sections["readme"] + separator +
            sections["architecture"] + separator +
            sections["api_section"] + separator +
            sections["classes_section"] + separator +
            sections["functions_section"] + separator +
            sections["data_models"] + separator +
            sections["deployment"] + separator +
            sections["quality_report"] + separator +
            sections["data_analysis"] +
            end_text
        )
