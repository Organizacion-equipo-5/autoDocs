import os
import json
import re
import requests
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# Asegurar carga de variables de entorno desde backend y raíz del proyecto
load_dotenv()
_backend_env = Path(__file__).resolve().parents[1] / '.env'
if _backend_env.exists():
    load_dotenv(_backend_env, override=False)
_root_env = Path(__file__).resolve().parents[2] / '.env'
if _root_env.exists():
    load_dotenv(_root_env, override=False)


class AIEnhancer:
    """
    Mejora la documentación técnica usando IA (Groq con modelos compatibles y fallback local Ollama).
    Genera descripciones más detalladas, explica patrones de diseño,
    y proporciona insights técnicos avanzados.
    """

    GROQ_CANDIDATE_MODELS = [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ]

    def __init__(self):
        # Soporte para múltiples API keys de Groq
        api_keys_str = os.getenv('GROQ_API_KEY', '')
        if api_keys_str:
            self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            print(f"[AI] Total de API keys de Groq cargadas: {len(self.api_keys)}")
        else:
            self.api_keys = []
            print("[AI] Aviso: No se encontró GROQ_API_KEY en variables de entorno")

        self.current_key_index = 0
        self.working_groq_model = None
        self.API_URL = "https://api.groq.com/openai/v1/chat/completions"
        self._ollama_model = None
        self._ollama_checked = False

    def get_api_key(self) -> Optional[str]:
        """Obtiene la API key actual con rotación."""
        if not self.api_keys:
            return None
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    def _check_ollama(self) -> Optional[str]:
        """Verifica si Ollama está corriendo en localhost y qué modelo está disponible."""
        if self._ollama_checked:
            return self._ollama_model
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            if r.status_code == 200:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                if models:
                    preferred = next((m for m in models if "mistral" in m.lower() or "llama" in m.lower() or "qwen" in m.lower()), models[0])
                    self._ollama_model = preferred
                    print(f"[AI] Servidor Ollama local detectado con modelo: {self._ollama_model}")
        except Exception:
            self._ollama_model = None
        self._ollama_checked = True
        return self._ollama_model

    def is_available(self) -> bool:
        """Verifica si alguna IA (Groq o Ollama local) está disponible."""
        return bool(self.api_keys) or bool(self._check_ollama())

    def _call_groq(self, system_prompt: str, user_prompt: str, max_tokens: int = 400) -> Optional[str]:
        """Intenta llamar a la API de Groq probando modelos compatibles y rotando keys."""
        if not self.api_keys:
            return None

        models_to_try = (
            [self.working_groq_model] + [m for m in self.GROQ_CANDIDATE_MODELS if m != self.working_groq_model]
            if self.working_groq_model else list(self.GROQ_CANDIDATE_MODELS)
        )

        for attempt in range(len(self.api_keys)):
            api_key = self.get_api_key()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "AutoDocs/1.0"
            }

            for model_name in models_to_try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                }
                try:
                    response = requests.post(self.API_URL, json=payload, headers=headers, timeout=25)
                    if response.status_code == 200:
                        result = response.json()
                        content = (
                            result.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                            .strip()
                        )
                        if content:
                            self.working_groq_model = model_name
                            print(f"[AI] Llamada exitosa con Groq ({model_name})")
                            return content
                    elif response.status_code == 429:
                        print(f"[AI] Groq rate-limit (429) en {model_name}, probando modelo alternativo...")
                        continue
                    elif response.status_code in [401, 403]:
                        print(f"[AI] Groq API key inválida o expirada #{attempt + 1}")
                        break
                    elif response.status_code == 404:
                        continue
                    else:
                        print(f"[AI] Groq HTTP {response.status_code} ({model_name}): {response.text[:120]}")
                except Exception as e:
                    print(f"[AI] Error llamando a Groq ({model_name}): {e}")
                    continue

        return None

    def _call_ollama(self, system_prompt: str, user_prompt: str, max_tokens: int = 400) -> Optional[str]:
        """Fallback local con Ollama si está disponible."""
        model = self._check_ollama()
        if not model:
            return None
        try:
            full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"
            payload = {
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7
                }
            }
            r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=15)
            if r.status_code == 200:
                ans = r.json().get("response", "").strip()
                if ans:
                    print(f"[AI] Llamada exitosa con Ollama local ({model})")
                    return ans
        except Exception as e:
            print(f"[AI] Error llamando a Ollama local: {e}")
        return None

    def _call_ai(self, system_prompt: str, user_prompt: str, max_tokens: int = 400) -> Optional[str]:
        """Ejecuta llamada de IA priorizando Groq y con fallback en Ollama local."""
        # 1. Intentar con Groq
        res = self._call_groq(system_prompt, user_prompt, max_tokens=max_tokens)
        if res:
            return res

        # 2. Fallback a Ollama local
        res = self._call_ollama(system_prompt, user_prompt, max_tokens=max_tokens)
        if res:
            return res

        print("[AI] No se pudo obtener respuesta de ninguna IA disponible")
        return None

    def enhance_function_description(self, function: dict, context: str = "") -> str:
        """
        Genera una descripción mejorada para una función usando IA.

        Args:
            function: Diccionario con información de la función
            context: Contexto adicional del proyecto

        Returns:
            Descripción mejorada de la función
        """
        if not self.is_available():
            return function.get('docstring', '') or f"Función {function['name']}"

        params = ', '.join(function.get('params', []))
        prompt = f"""Analiza esta función y genera una descripción sencilla y comprensible para personas no técnicas:

Nombre: {function['name']}
Parámetros: {params}
Archivo: {function.get('file', 'desconocido')}
Docstring existente: {function.get('docstring', 'ninguna')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito de la función en lenguaje simple (explicado como si fuera para alguien sin conocimientos de programación)
2. Qué datos necesita para funcionar (explicado de forma sencilla)
3. Qué resultado produce (explicado de forma sencilla)
4. Para qué se usa en la vida real (ejemplos prácticos)
5. Importancia de esta función en el sistema

Usa lenguaje claro, evita términos técnicos complejos, y explica los conceptos de forma sencilla. Mantén la descripción concisa pero técnica (máximo 150 palabras)."""

        result = self._call_ai(
            "Eres un experto en documentación técnica de software. Genera descripciones claras, precisas y técnicas.",
            prompt,
            max_tokens=300
        )
        if result:
            return result

        print(f"[AI] No se pudo mejorar descripción de función: {function['name']}")
        return function.get('docstring', '') or f"Función {function['name']}"

    def enhance_class_description(self, class_info: dict, context: str = "") -> str:
        """
        Genera una descripción mejorada para una clase usando IA.

        Args:
            class_info: Diccionario con información de la clase
            context: Contexto adicional del proyecto

        Returns:
            Descripción mejorada de la clase
        """
        if not self.is_available():
            return class_info.get('docstring', '') or f"Clase {class_info['name']}"

        methods = ', '.join(class_info.get('methods', [])[:10])
        bases = ', '.join(class_info.get('bases', []))

        prompt = f"""Analiza esta clase y genera una descripción sencilla y comprensible para personas no técnicas:

Nombre: {class_info['name']}
Hereda de: {bases or 'object'}
Métodos: {methods}
Archivo: {class_info.get('file', 'desconocido')}
Docstring existente: {class_info.get('docstring', 'ninguna')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito de la clase en lenguaje simple (explicado como si fuera para alguien sin conocimientos de programación)
2. Qué representa esta clase en el sistema (analogías con el mundo real si es posible)
3. Qué puede hacer esta clase (funcionalidades principales explicadas de forma sencilla)
4. Para qué se usa en la vida real (ejemplos prácticos)
5. Importancia de esta clase en el sistema

Usa lenguaje claro, evita términos técnicos complejos, y explica los conceptos de forma sencilla."""

        result = self._call_ai(
            "Eres un experto en explicar conceptos técnicos de forma sencilla para personas sin conocimientos de programación. Genera descripciones claras, comprensibles y prácticas.",
            prompt,
            max_tokens=300
        )
        if result:
            return result

        print(f"[AI] No se pudo mejorar descripción de clase: {class_info['name']}")
        return class_info.get('docstring', '') or f"Clase {class_info['name']}"

    def enhance_endpoint_description(self, endpoint: dict, context: str = "") -> str:
        """
        Genera una descripción mejorada para un endpoint de API usando IA.

        Args:
            endpoint: Diccionario con información del endpoint
            context: Contexto adicional del proyecto

        Returns:
            Descripción mejorada del endpoint
        """
        if not self.is_available():
            return f"Endpoint {endpoint.get('method')} {endpoint.get('path')}"

        prompt = f"""Analiza este endpoint de API y genera una descripción sencilla y comprensible para personas no técnicas:

Método: {endpoint.get('method')}
Ruta: {endpoint.get('path')}
Framework: {endpoint.get('framework', 'desconocido')}
Archivo: {endpoint.get('file', 'desconocido')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito del endpoint en lenguaje simple (explicado como si fuera para alguien sin conocimientos de programación)
2. Qué hace este endpoint (funcionalidad explicada de forma sencilla)
3. Qué información necesita para funcionar (explicado de forma sencilla)
4. Qué resultado devuelve (explicado de forma sencilla)
5. Para qué se usa en la vida real (ejemplos prácticos)

Usa lenguaje claro, evita términos técnicos complejos, y explica los conceptos de forma sencilla."""

        result = self._call_ai(
            "Eres un experto en explicar conceptos técnicos de forma sencilla para personas sin conocimientos de programación. Genera descripciones claras, comprensibles y prácticas.",
            prompt,
            max_tokens=300
        )
        if result:
            return result

        print(f"[AI] No se pudo mejorar descripción de endpoint: {endpoint.get('path')}")
        return f"Endpoint {endpoint.get('method')} {endpoint.get('path')}"

    def generate_architecture_insights(self, analysis_results: dict) -> str:
        """
        Genera insights sobre la arquitectura del proyecto usando IA.

        Args:
            analysis_results: Resultados del análisis del proyecto

        Returns:
            Insights sobre arquitectura y patrones detectados
        """
        if not self.is_available():
            return "Insights de IA no disponibles - configura GEMINI_API_KEY en el archivo .env"

        lang = analysis_results.get('primary_language', 'desconocido')
        langs = analysis_results.get('languages', {})
        functions = analysis_results.get('functions', [])
        classes = analysis_results.get('classes', [])
        endpoints = analysis_results.get('endpoints', [])

        prompt = f"""Analiza esta información de un proyecto de software y genera insights arquitectónicos:

Lenguaje principal: {lang}
Lenguajes detectados: {langs}
Total funciones: {len(functions)}
Total clases: {len(classes)}
Total endpoints: {len(endpoints)}

Genera insights sobre:
1. Patrones arquitectónicos probables (MVC, Microservicios, Monolito, etc.)
2. Buenas prácticas detectadas
3. Áreas de mejora sugeridas
4. Complejidad del proyecto
5. Recomendaciones de escalabilidad

Mantén los insights concisos y accionables (máximo 200 palabras)."""

        result = self._call_ai(
            "Eres un arquitecto de software senior. Genera insights técnicos y prácticos sobre arquitectura de proyectos.",
            prompt,
            max_tokens=400
        )
        if result:
            return result

        print("[AI] No se pudieron generar insights de arquitectura")
        return "No se pudieron generar insights de arquitectura"

    def enhance_documentation(self, analysis_results: dict) -> dict:
        """
        Mejora toda la documentación del proyecto usando IA (Gemini).

        Args:
            analysis_results: Resultados del análisis del proyecto

        Returns:
            Resultados con descripciones mejoradas por IA
        """
        if not self.is_available():
            print("[AI] Groq no configurado, usando documentación básica. "
                  "Agrega GEMINI_API_KEY en tu archivo .env para habilitar la mejora con IA.")
            return analysis_results

        print("[AI] Mejorando documentación con Groq...")

        # Contexto del proyecto
        context = (
            f"Proyecto en {analysis_results.get('primary_language', 'desconocido')} "
            f"con {len(analysis_results.get('functions', []))} funciones"
        )

        # Mejorar funciones (limitar a 5 para reducir consumo de tokens)
        for func in analysis_results.get('functions', [])[:5]:
            func['ai_description'] = self.enhance_function_description(func, context)

        # Mejorar clases (limitar a 3)
        for cls in analysis_results.get('classes', [])[:3]:
            cls['ai_description'] = self.enhance_class_description(cls, context)

        # Mejorar endpoints (limitar a 3)
        for ep in analysis_results.get('endpoints', [])[:3]:
            ep['ai_description'] = self.enhance_endpoint_description(ep, context)

        # Generar insights de arquitectura
        analysis_results['ai_architecture_insights'] = self.generate_architecture_insights(analysis_results)

        print("[AI] Documentación mejorada exitosamente con Gemini")
        return analysis_results

    def enhance_database_analysis(self, raw_sql: str, metadata: dict) -> str:
        """Genera un resumen de análisis de base de datos usando Groq."""
        if not self.is_available():
            return "Resumen de IA no disponible - configura GROQ_API_KEY en el archivo .env"

        prompt = f"""Analiza este esquema SQL y genera un informe técnico en español que incluya:
- Un resumen del propósito del esquema.
- Identificación de tipos de fuentes de datos: estructurados, semi-estructurados y no estructurados.
- Si el esquema sugiere un modelo de Data Warehouse, indica si es tipo estrella o copo de nieve.
- Recomendaciones breves de modelado de datos y minería de datos.

Esquema SQL:
{raw_sql}

Metadatos:
Tablas: {metadata['tables']}
Datos estructurados: {metadata['data_sources']['structured']}
Datos semi-estructurados: {metadata['data_sources']['semi_structured']}
Datos no estructurados: {metadata['data_sources']['unstructured']}
Esquema de Data Warehouse sugerido: {metadata['warehouse_schema']['type']}
Descripción de esquema: {metadata['warehouse_schema']['description']}

Responde en formato de párrafo corto y técnico, usando lenguaje claro y profesional. No devuelvas JSON."""

        result = self._call_ai(
            "Eres un experto en análisis de bases de datos y minería de datos. Genera un informe técnico y claro para un equipo de datos.",
            prompt,
            max_tokens=450
        )
        return result or "Resumen de IA no disponible - no se recibió respuesta de Groq."

    def enhance_database_report_sections(self, sections: dict) -> dict:
        """Mejora la redacción de las secciones del informe de base de datos usando Groq."""
        if not self.is_available():
            return {}

        prompt = f"""Mejora la redacción de este informe de análisis SQL en español.
Mantén el significado técnico exacto, pero redacta de forma clara, profesional y coherente.
No inventes tablas, columnas ni relaciones que no estén en los datos de entrada.

Datos de entrada:
Resumen: {sections.get('summary', '')}
Tablas detectadas: {sections.get('tables', [])}
Preparación de datos: {sections.get('data_preparation', [])}
Minería de datos: {sections.get('data_mining_insights', [])}
Recomendaciones: {sections.get('suggestions', [])}
Descripción de Data Warehouse: {sections.get('warehouse_description', '')}

Responde SOLO con JSON válido con esta estructura:
{{
  "summary": "texto del resumen mejorado",
  "data_preparation": ["item 1", "item 2"],
  "data_mining_insights": ["item 1", "item 2"],
  "suggestions": ["item 1", "item 2"],
  "warehouse_description": "texto mejorado"
}}"""

        result = self._call_ai(
            "Eres un experto en bases de datos y redacción técnica. "
            "Devuelves únicamente JSON válido, sin markdown ni texto adicional.",
            prompt,
            max_tokens=900
        )
        if not result:
            return {}

        cleaned = result.strip()
        if cleaned.startswith('```'):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as e:
            print(f"[AI DB Sections] JSON inválido: {e}")

        return {}

    def mine_code_patterns(self, analysis_results: dict) -> dict:
        """
        Aplica conceptos de minería de datos al código:
        - Detección de patrones frecuentes (funciones similares)
        - Clasificación de módulos por complejidad
        - Clustering de archivos por lenguaje/función

        Args:
            analysis_results: Resultados del análisis del proyecto

        Returns:
            Diccionario con patrones minados del código
        """
        print("[AI] Iniciando mine_code_patterns...")
        if not self.is_available():
            print("[AI] ERROR: AI Enhancer no está disponible (sin API keys)")
            return {
                "frequent_patterns": [],
                "complexity_clusters": [],
                "function_clusters": [],
                "insights": "Minería de patrones no disponible - configura GROQ_API_KEY"
            }

        print("[AI] AI Enhancer está disponible, procediendo con minería de patrones...")
        functions = analysis_results.get("functions", [])
        classes = analysis_results.get("classes", [])
        structure = analysis_results.get("structure", [])

        print(f"[AI] Funciones: {len(functions)}, Clases: {len(classes)}, Estructura: {len(structure)}")

        # Extraer información para análisis
        function_names = [f["name"] for f in functions]
        class_names = [c["name"] for c in classes]
        file_paths = [s["path"] for s in structure]

        prompt = f"""Analiza este código y aplica técnicas de minería de datos para detectar patrones. Genera un análisis sencillo y comprensible para personas no técnicas:

Funciones detectadas ({len(function_names)}): {function_names[:20]}
Clases detectadas ({len(class_names)}): {class_names[:15]}
Archivos del proyecto ({len(file_paths)}): {file_paths[:15]}

Genera un análisis que incluya:
1. **Patrones frecuentes**: Nombres o estructuras de funciones que se repiten (explicados de forma sencilla)
2. **Clustering por complejidad**: Agrupa funciones en categorías (baja, media, alta complejidad) con explicaciones sencillas
3. **Clustering por funcionalidad**: Agrupa archivos/módulos por su propósito (explicado de forma sencilla)
4. **Anomalías**: Funciones o clases que no siguen el patrón general del proyecto (explicado de forma sencilla)

Formato de respuesta JSON:
{{
    "frequent_patterns": [
        {{"pattern": "nombre_patron", "description": "explicación sencilla del patrón", "frequency": 5, "examples": ["func1", "func2"]}}
    ],
    "complexity_clusters": [
        {{"cluster": "baja", "description": "explicación sencilla", "count": 10, "avg_complexity": 2}},
        {{"cluster": "media", "description": "explicación sencilla", "count": 5, "avg_complexity": 7}},
        {{"cluster": "alta", "description": "explicación sencilla", "count": 2, "avg_complexity": 15}}
    ],
    "function_clusters": [
        {{"cluster": "controllers", "description": "explicación sencilla", "files": ["file1", "file2"], "functions": ["func1", "func2"]}}
    ],
    "anomalies": [
        {{"type": "funcion", "name": "nombre", "description": "explicación sencilla del motivo"}}
    ]
}}

Responde solo con el JSON, sin texto adicional. Usa lenguaje claro y evita términos técnicos complejos."""

        result = self._call_ai(
            "Eres un experto en explicar conceptos técnicos de minería de datos de forma sencilla para personas sin conocimientos de programación. Genera análisis JSON estructurados con descripciones claras y comprensibles.",
            prompt,
            max_tokens=600
        )

        if result:
            try:
                import json
                # Intentar extraer JSON de la respuesta
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = result[json_start:json_end]
                    patterns = json.loads(json_str)
                    patterns["insights"] = "Análisis de minería de datos completado exitosamente"
                    return patterns
            except Exception as e:
                print(f"[AI] Error al parsear JSON de minería de patrones: {e}")

        # Fallback: análisis simple sin IA
        return self._mine_patterns_simple(analysis_results)

    def _mine_patterns_simple(self, analysis_results: dict) -> dict:
        """
        Realiza minería de patrones simple sin IA (fallback).
        """
        functions = analysis_results.get("functions", [])
        classes = analysis_results.get("classes", [])
        structure = analysis_results.get("structure", [])

        # Detectar patrones frecuentes en nombres de funciones
        from collections import Counter
        prefixes = []
        for f in functions:
            name = f["name"].lower()
            for prefix in ["get_", "post_", "put_", "delete_", "create_", "update_", "find_", "save_", "validate_", "check_"]:
                if name.startswith(prefix):
                    prefixes.append(prefix)

        prefix_counts = Counter(prefixes)
        frequent_patterns = [
            {"pattern": prefix, "frequency": count, "examples": f"Operaciones {prefix} repetidas"}
            for prefix, count in prefix_counts.most_common(5)
        ]

        # Clustering por complejidad
        low_cx = [f for f in functions if f.get("complexity", 1) <= 5]
        med_cx = [f for f in functions if 5 < f.get("complexity", 1) <= 10]
        high_cx = [f for f in functions if f.get("complexity", 1) > 10]

        complexity_clusters = [
            {"cluster": "baja", "count": len(low_cx), "avg_complexity": round(sum(f.get("complexity", 1) for f in low_cx) / max(len(low_cx), 1), 2)},
            {"cluster": "media", "count": len(med_cx), "avg_complexity": round(sum(f.get("complexity", 1) for f in med_cx) / max(len(med_cx), 1), 2)},
            {"cluster": "alta", "count": len(high_cx), "avg_complexity": round(sum(f.get("complexity", 1) for f in high_cx) / max(len(high_cx), 1), 2)},
        ]

        # Clustering por directorio
        dir_clusters = {}
        for item in structure:
            path = item["path"]
            parts = path.replace("\\", "/").split("/")
            if len(parts) > 1:
                dir_name = parts[0]
                if dir_name not in dir_clusters:
                    dir_clusters[dir_name] = []
                dir_clusters[dir_name].append(path)

        function_clusters = [
            {"cluster": dir_name, "files": files, "count": len(files)}
            for dir_name, files in list(dir_clusters.items())[:10]
        ]

        return {
            "frequent_patterns": frequent_patterns,
            "complexity_clusters": complexity_clusters,
            "function_clusters": function_clusters,
            "anomalies": [],
            "insights": "Análisis de minería de datos completado (modo simple sin IA)"
        }