import os
import json
import urllib.request
import urllib.error
from typing import Optional


class AIEnhancer:
    """
    Mejora la documentación técnica usando IA (Google Gemini).
    Genera descripciones más detalladas, explica patrones de diseño,
    y proporciona insights técnicos avanzados.
    """

    GEMINI_API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')

    def is_available(self) -> bool:
        """Verifica si la API de Gemini está configurada y disponible."""
        return bool(self.api_key)

    def _call_gemini(self, system_prompt: str, user_prompt: str, max_tokens: int = 400):
        if not self.is_available():
            return None

        payload = {
            "model": "google/gemma-4-31b:free",
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

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.GEMINI_API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))

                return (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print(f"[AI OpenRouter] HTTP {e.code}: {body[:300]}")
        except Exception as e:
            print(f"[AI OpenRouter] Error: {e}")

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
        prompt = f"""Analiza esta función y genera una descripción técnica profesional:

Nombre: {function['name']}
Parámetros: {params}
Archivo: {function.get('file', 'desconocido')}
Docstring existente: {function.get('docstring', 'ninguna')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito de la función
2. Qué parámetros recibe y su función
3. Qué retorna (si es inferible)
4. Casos de uso típicos
5. Notas importantes sobre su implementación

Mantén la descripción concisa pero técnica (máximo 150 palabras)."""

        result = self._call_gemini(
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

        prompt = f"""Analiza esta clase y genera una descripción técnica profesional:

Nombre: {class_info['name']}
Hereda de: {bases or 'object'}
Métodos: {methods}
Archivo: {class_info.get('file', 'desconocido')}
Docstring existente: {class_info.get('docstring', 'ninguna')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito y responsabilidad de la clase
2. Patrones de diseño que implementa (si aplica)
3. Relación con otras clases (herencia, composición)
4. Métodos principales y su función
5. Casos de uso típicos

Mantén la descripción concisa pero técnica (máximo 150 palabras)."""

        result = self._call_gemini(
            "Eres un experto en documentación técnica de software. Genera descripciones claras, precisas y técnicas.",
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

        prompt = f"""Analiza este endpoint de API y genera una descripción técnica profesional:

Método: {endpoint.get('method')}
Ruta: {endpoint.get('path')}
Framework: {endpoint.get('framework', 'desconocido')}
Archivo: {endpoint.get('file', 'desconocido')}
Contexto del proyecto: {context}

Genera una descripción que incluya:
1. Propósito del endpoint
2. Qué recursos manipula
3. Parámetros esperados (query params, body, headers)
4. Respuestas típicas y códigos de estado
5. Casos de uso y consideraciones de seguridad

Mantén la descripción concisa pero técnica (máximo 150 palabras)."""

        result = self._call_gemini(
            "Eres un experto en documentación de APIs REST. Genera descripciones claras, precisas y técnicas.",
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

        result = self._call_gemini(
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
            print("[AI] Gemini no configurado, usando documentación básica. "
                  "Agrega GEMINI_API_KEY en tu archivo .env para habilitar la mejora con IA.")
            return analysis_results

        print("[AI] Mejorando documentación con Gemini...")

        # Contexto del proyecto
        context = (
            f"Proyecto en {analysis_results.get('primary_language', 'desconocido')} "
            f"con {len(analysis_results.get('functions', []))} funciones"
        )

        # Mejorar funciones (limitar a 20 para no exceder cuotas)
        for func in analysis_results.get('functions', [])[:20]:
            if not func.get('docstring'):
                func['ai_description'] = self.enhance_function_description(func, context)

        # Mejorar clases (limitar a 15)
        for cls in analysis_results.get('classes', [])[:15]:
            if not cls.get('docstring'):
                cls['ai_description'] = self.enhance_class_description(cls, context)

        # Mejorar endpoints (limitar a 15)
        for ep in analysis_results.get('endpoints', [])[:15]:
            ep['ai_description'] = self.enhance_endpoint_description(ep, context)

        # Generar insights de arquitectura
        analysis_results['ai_architecture_insights'] = self.generate_architecture_insights(analysis_results)

        print("[AI] Documentación mejorada exitosamente con Gemini")
        return analysis_results