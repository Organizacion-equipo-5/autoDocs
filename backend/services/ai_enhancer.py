import os
import json
import requests
from typing import Optional, List


class AIEnhancer:
    """
    Mejora la documentación técnica usando IA (Google Gemini).
    Genera descripciones más detalladas, explica patrones de diseño,
    y proporciona insights técnicos avanzados.
    """

    def __init__(self):
        # Soporte para múltiples API keys
        api_keys_str = os.getenv('GROQ_API_KEY', '')
        print(f"[AI] GROQ_API_KEY encontrada: {bool(api_keys_str)}")
        if api_keys_str:
            # Separar por comas si hay múltiples keys
            self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            print(f"[AI] Total de API keys cargadas: {len(self.api_keys)}")
        else:
            self.api_keys = []
            print("[AI] WARNING: No se encontró GROQ_API_KEY")
        
        self.current_key_index = 0
        self.API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def get_api_key(self) -> Optional[str]:
        """Obtiene la API key actual con rotación."""
        if not self.api_keys:
            return None
        
        key = self.api_keys[self.current_key_index]
        # Rotar a la siguiente key para la siguiente llamada
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    def is_available(self) -> bool:
        """Verifica si la API de Gemini está configurada y disponible."""
        return bool(self.api_keys)

    def _call_ai(self, system_prompt: str, user_prompt: str, max_tokens: int = 400):
        if not self.is_available():
            print("[AI] GROQ_API_KEY no está configurada")
            return None

        # Intentar con cada API key disponible hasta que una funcione
        for attempt in range(len(self.api_keys)):
            api_key = self.get_api_key()
            
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "AutoDocs/1.0"
            }

            try:
                response = requests.post(
                    self.API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30,
                    verify=True
                )

                if response.status_code == 200:
                    result = response.json()
                    content = (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if content:
                        print(f"[AI] Llamada exitosa con API key #{attempt + 1}")
                        return content
                else:
                    print(f"[AI] HTTP Error con API key #{attempt + 1}: {response.status_code} - {response.text[:200]}")
                    # Si es error de autenticación, intentar con la siguiente key
                    if response.status_code in [401, 403]:
                        continue
                    # Si es otro error, retornar None
                    return None

            except Exception as e:
                print(f"[AI] Error llamando a la API con key #{attempt + 1}: {e}")
                # Si es error de conexión, intentar con la siguiente key
                continue

        print("[AI] Todas las API keys fallaron")
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