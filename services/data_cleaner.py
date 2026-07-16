"""
Servicio de limpieza de datos para el análisis de proyectos.

Este módulo proporciona técnicas de limpieza de datos aplicables a:
- Código fuente analizado
- Datasets subidos (CSV/JSON)
- Datos estructurados detectados
"""

from typing import List, Dict, Any, Optional
import re
from collections import Counter


class DataCleaner:
    """
    Aplica técnicas de limpieza de datos al código fuente y datasets.
    """

    def __init__(self):
        self.cleaning_report = {
            "duplicates_removed": 0,
            "missing_values_filled": 0,
            "strings_normalized": 0,
            "outliers_detected": {},
            "inconsistencies_fixed": 0
        }

    def remove_duplicates(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Elimina registros duplicados basándose en todos los campos.

        Args:
            data: Lista de diccionarios con datos

        Returns:
            Lista sin duplicados
        """
        if not data:
            return data

        # Convertir cada registro a una tupla ordenada para comparación
        seen = set()
        unique_data = []

        for item in data:
            # Crear una representación hashable del item
            item_tuple = tuple(sorted((k, str(v)) for k, v in item.items()))
            if item_tuple not in seen:
                seen.add(item_tuple)
                unique_data.append(item)

        duplicates_removed = len(data) - len(unique_data)
        self.cleaning_report["duplicates_removed"] += duplicates_removed

        return unique_data

    def remove_duplicates_by_field(self, data: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
        """
        Elimina duplicados basándose en un campo específico.

        Args:
            data: Lista de diccionarios con datos
            field: Campo usado para identificar duplicados

        Returns:
            Lista sin duplicados en el campo especificado
        """
        if not data or field not in (data[0].keys() if data else []):
            return data

        seen_values = set()
        unique_data = []

        for item in data:
            value = item.get(field)
            if value not in seen_values:
                seen_values.add(value)
                unique_data.append(item)

        duplicates_removed = len(data) - len(unique_data)
        self.cleaning_report["duplicates_removed"] += duplicates_removed

        return unique_data

    def fill_missing_values(self, data: List[Dict[str, Any]], strategy: str = "default") -> List[Dict[str, Any]]:
        """
        Rellena valores faltantes según la estrategia especificada.

        Estrategias:
        - 'default': Usa valor por defecto (None, 0, "")
        - 'mean': Usa el promedio para numéricos
        - 'median': Usa la mediana para numéricos
        - 'mode': Usa el valor más frecuente
        - 'forward_fill': Usa el último valor válido

        Args:
            data: Lista de diccionarios con datos
            strategy: Estrategia de relleno

        Returns:
            Lista con valores faltantes rellenados
        """
        if not data:
            return data

        filled_data = []
        missing_count = 0

        # Calcular estadísticas por campo
        field_stats = {}
        for item in data:
            for key, value in item.items():
                if key not in field_stats:
                    field_stats[key] = []
                if value is not None and value != "":
                    field_stats[key].append(value)

        # Calcular valores de relleno según estrategia
        fill_values = {}
        for key, values in field_stats.items():
            if strategy == "mean" and all(isinstance(v, (int, float)) for v in values):
                fill_values[key] = sum(values) / len(values)
            elif strategy == "median" and all(isinstance(v, (int, float)) for v in values):
                sorted_values = sorted(values)
                n = len(sorted_values)
                fill_values[key] = sorted_values[n // 2] if n % 2 == 1 else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
            elif strategy == "mode":
                counter = Counter(values)
                fill_values[key] = counter.most_common(1)[0][0] if counter else None
            elif strategy == "forward_fill":
                fill_values[key] = values[-1] if values else None
            else:  # default
                fill_values[key] = None

        # Aplicar relleno
        for item in data:
            filled_item = {}
            for key, value in item.items():
                if value is None or value == "":
                    filled_item[key] = fill_values.get(key)
                    missing_count += 1
                else:
                    filled_item[key] = value
            filled_data.append(filled_item)

        self.cleaning_report["missing_values_filled"] += missing_count
        return filled_data

    def normalize_strings(self, data: List[Dict[str, Any]], fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Normaliza cadenas de texto: trim, lowercase, remove special chars.

        Args:
            data: Lista de diccionarios con datos
            fields: Campos específicos a normalizar (None = todos los string fields)

        Returns:
            Lista con cadenas normalizadas
        """
        if not data:
            return data

        normalized_data = []
        normalized_count = 0

        for item in data:
            normalized_item = {}
            for key, value in item.items():
                if fields and key not in fields:
                    normalized_item[key] = value
                    continue

                if isinstance(value, str):
                    # Trim whitespace
                    normalized = value.strip()
                    # Convertir a lowercase si es apropiado
                    if not re.search(r'[A-Z]{2,}', normalized):  # No si parece acrónimo
                        normalized = normalized.lower()
                    # Remover caracteres especiales excepto guiones y espacios
                    normalized = re.sub(r'[^\w\s-]', '', normalized)
                    # Remover espacios múltiples
                    normalized = re.sub(r'\s+', ' ', normalized)

                    if normalized != value:
                        normalized_count += 1
                    normalized_item[key] = normalized
                else:
                    normalized_item[key] = value
            normalized_data.append(normalized_item)

        self.cleaning_report["strings_normalized"] += normalized_count
        return normalized_data

    def detect_outliers(self, data: List[Dict[str, Any]], column: str, method: str = "iqr") -> Dict[str, Any]:
        """
        Detecta valores atípicos en una columna numérica.

        Métodos:
        - 'iqr': Rango intercuartílico
        - 'zscore': Z-score (desviación estándar)
        - 'percentile': Percentiles (1% y 99%)

        Args:
            data: Lista de diccionarios con datos
            column: Columna a analizar
            method: Método de detección

        Returns:
            Diccionario con información de outliers
        """
        if not data or column not in (data[0].keys() if data else []):
            return {"column": column, "outliers": [], "count": 0, "method": method}

        # Extraer valores numéricos
        values = []
        for item in data:
            val = item.get(column)
            if isinstance(val, (int, float)):
                values.append(val)

        if not values:
            return {"column": column, "outliers": [], "count": 0, "method": method}

        outliers = []
        outlier_indices = []

        if method == "iqr":
            # Método del rango intercuartílico
            sorted_values = sorted(values)
            n = len(sorted_values)
            q1 = sorted_values[n // 4]
            q3 = sorted_values[3 * n // 4]
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            for i, item in enumerate(data):
                val = item.get(column)
                if isinstance(val, (int, float)):
                    if val < lower_bound or val > upper_bound:
                        outliers.append(val)
                        outlier_indices.append(i)

        elif method == "zscore":
            # Método Z-score
            import statistics
            mean = statistics.mean(values)
            stdev = statistics.stdev(values) if len(values) > 1 else 1
            threshold = 3  # 3 desviaciones estándar

            for i, item in enumerate(data):
                val = item.get(column)
                if isinstance(val, (int, float)):
                    zscore = abs((val - mean) / stdev) if stdev > 0 else 0
                    if zscore > threshold:
                        outliers.append(val)
                        outlier_indices.append(i)

        elif method == "percentile":
            # Método de percentiles
            sorted_values = sorted(values)
            n = len(sorted_values)
            p1 = sorted_values[int(n * 0.01)]
            p99 = sorted_values[int(n * 0.99)]

            for i, item in enumerate(data):
                val = item.get(column)
                if isinstance(val, (int, float)):
                    if val < p1 or val > p99:
                        outliers.append(val)
                        outlier_indices.append(i)

        result = {
            "column": column,
            "method": method,
            "count": len(outliers),
            "outliers": outliers,
            "indices": outlier_indices,
            "percentage": round(len(outliers) / len(data) * 100, 2) if data else 0
        }

        self.cleaning_report["outliers_detected"][column] = result
        return result

    def detect_inconsistencies(self, data: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detecta inconsistencias basadas en reglas de negocio.

        Args:
            data: Lista de diccionarios con datos
            rules: Lista de reglas de validación
                  Ej: [{"field": "age", "min": 0, "max": 120}]

        Returns:
            Lista de inconsistencias detectadas
        """
        if not data or not rules:
            return []

        inconsistencies = []

        for i, item in enumerate(data):
            for rule in rules:
                field = rule.get("field")
                if field not in item:
                    continue

                value = item[field]

                # Validación de rango
                if "min" in rule and isinstance(value, (int, float)):
                    if value < rule["min"]:
                        inconsistencies.append({
                            "index": i,
                            "field": field,
                            "value": value,
                            "rule": f"min={rule['min']}",
                            "message": f"Valor {value} menor al mínimo {rule['min']}"
                        })

                if "max" in rule and isinstance(value, (int, float)):
                    if value > rule["max"]:
                        inconsistencies.append({
                            "index": i,
                            "field": field,
                            "value": value,
                            "rule": f"max={rule['max']}",
                            "message": f"Valor {value} mayor al máximo {rule['max']}"
                        })

                # Validación de patrón regex
                if "pattern" in rule and isinstance(value, str):
                    if not re.match(rule["pattern"], value):
                        inconsistencies.append({
                            "index": i,
                            "field": field,
                            "value": value,
                            "rule": f"pattern={rule['pattern']}",
                            "message": f"Valor '{value}' no coincide con el patrón esperado"
                        })

                # Validación de valores permitidos
                if "allowed_values" in rule:
                    if value not in rule["allowed_values"]:
                        inconsistencies.append({
                            "index": i,
                            "field": field,
                            "value": value,
                            "rule": f"allowed={rule['allowed_values']}",
                            "message": f"Valor '{value}' no está en los valores permitidos"
                        })

        self.cleaning_report["inconsistencies_fixed"] = len(inconsistencies)
        return inconsistencies

    def clean_code_issues(self, code_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplica limpieza a los resultados del análisis de código.

        Args:
            code_analysis: Resultados del análisis del proyecto

        Returns:
            Diccionario con problemas de código detectados
        """
        issues = {
            "missing_docstrings": [],
            "high_complexity": [],
            "naming_conventions": [],
            "unused_imports": []
        }

        # Detectar funciones sin docstring
        for func in code_analysis.get("functions", []):
            if not func.get("docstring"):
                issues["missing_docstrings"].append({
                    "name": func.get("name"),
                    "file": func.get("file"),
                    "line": func.get("line")
                })

        # Detectar funciones de alta complejidad
        for func in code_analysis.get("functions", []):
            complexity = func.get("complexity", 1)
            if complexity > 10:
                issues["high_complexity"].append({
                    "name": func.get("name"),
                    "file": func.get("file"),
                    "complexity": complexity
                })

        # Detectar problemas de naming conventions
        for cls in code_analysis.get("classes", []):
            name = cls.get("name", "")
            if not name[0].isupper():
                issues["naming_conventions"].append({
                    "type": "class",
                    "name": name,
                    "file": cls.get("file"),
                    "message": "Las clases deben empezar con mayúscula (PascalCase)"
                })

        return issues

    def get_cleaning_report(self) -> Dict[str, Any]:
        """
        Retorna el reporte de operaciones de limpieza realizadas.

        Returns:
            Diccionario con estadísticas de limpieza
        """
        return self.cleaning_report

    def reset_report(self):
        """Reinicia el reporte de limpieza."""
        self.cleaning_report = {
            "duplicates_removed": 0,
            "missing_values_filled": 0,
            "strings_normalized": 0,
            "outliers_detected": {},
            "inconsistencies_fixed": 0
        }
