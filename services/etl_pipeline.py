"""
Pipeline ETL (Extract, Transform, Load) para el análisis de proyectos.

Este módulo implementa un pipeline completo ETL que integra:
- Extracción de datos desde múltiples fuentes (zip, github, csv, json)
- Transformación de datos (limpieza, normalización, enriquecimiento con IA)
- Carga de datos a múltiples destinos (mongodb, html, pdf)
"""

import os
import json
import csv
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from services.analyzer import ProjectAnalyzer
from services.file_handler import clone_github_repo, save_uploaded_project, classify_file_type
from services.data_cleaner import DataCleaner
from services.ai_enhancer import AIEnhancer
from services.doc_generator import DocGenerator
from services.exporter import DocumentExporter


class ETLPipeline:
    """
    Pipeline ETL completo para análisis y documentación de proyectos.
    """

    def __init__(self):
        self.data_cleaner = DataCleaner()
        self.ai_enhancer = AIEnhancer()
        self.pipeline_log = []

    def log(self, stage: str, message: str):
        """Registra un evento en el log del pipeline."""
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{stage}] {message}"
        self.pipeline_log.append(log_entry)
        print(log_entry)

    def extract(self, source_type: str, source_path: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extrae datos desde múltiples fuentes.

        Tipos de extracción:
        - 'zip': archivo comprimido (ya existe en file_handler)
        - 'github': repositorio remoto (ya existe en file_handler)
        - 'csv': dataset tabular
        - 'json': datos semiestructurados
        - 'directory': directorio local

        Args:
            source_type: Tipo de fuente de datos
            source_path: Ruta o URL de la fuente
            project_id: ID del proyecto (para uploads)

        Returns:
            Diccionario con datos extraídos y metadatos
        """
        self.log("EXTRACT", f"Iniciando extracción desde {source_type}: {source_path}")

        extracted_data = {
            "source_type": source_type,
            "source_path": source_path,
            "extracted_at": datetime.utcnow().isoformat(),
            "data": None,
            "metadata": {}
        }

        try:
            if source_type == "github":
                if not project_id:
                    raise ValueError("project_id es requerido para fuentes github")
                project_path = clone_github_repo(source_path, project_id)
                extracted_data["project_path"] = project_path
                extracted_data["metadata"]["repo_url"] = source_path

            elif source_type == "zip":
                if not project_id:
                    raise ValueError("project_id es requerido para fuentes zip")
                # Para zip, source_path debe ser el archivo
                from werkzeug.datastructures import FileStorage
                # Simular archivo FileStorage (en producción vendría del request)
                project_path = f"./uploads/{project_id}"
                extracted_data["project_path"] = project_path

            elif source_type == "csv":
                data = self._extract_csv(source_path)
                extracted_data["data"] = data
                extracted_data["metadata"]["rows"] = len(data)
                extracted_data["metadata"]["columns"] = list(data[0].keys()) if data else []

            elif source_type == "json":
                data = self._extract_json(source_path)
                extracted_data["data"] = data
                extracted_data["metadata"]["type"] = type(data).__name__

            elif source_type == "directory":
                project_path = source_path
                extracted_data["project_path"] = project_path

            else:
                raise ValueError(f"Tipo de fuente no soportado: {source_type}")

            self.log("EXTRACT", f"Extracción completada exitosamente")
            return extracted_data

        except Exception as e:
            self.log("EXTRACT", f"Error en extracción: {str(e)}")
            extracted_data["error"] = str(e)
            return extracted_data

    def _extract_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """Extrae datos de un archivo CSV."""
        data = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(dict(row))
        return data

    def _extract_json(self, file_path: str) -> Any:
        """Extrae datos de un archivo JSON."""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return json.load(f)

    def transform(self, raw_data: Dict[str, Any], rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Aplica transformaciones a los datos extraídos.

        Transformaciones disponibles:
        - Normalización de nombres
        - Eliminación de duplicados
        - Conversión de tipos
        - Enriquecimiento con IA (ya tienes ai_enhancer)
        - Limpieza de datos (data_cleaner)

        Args:
            raw_data: Datos extraídos en la fase Extract
            rules: Lista de reglas de transformación

        Returns:
            Diccionario con datos transformados
        """
        self.log("TRANSFORM", "Iniciando transformación de datos")

        transformed_data = {
            "transformed_at": datetime.utcnow().isoformat(),
            "data": raw_data.get("data"),
            "analysis_results": None,
            "cleaning_report": None,
            "mining_results": None
        }

        try:
            # Si es un proyecto de código, analizarlo
            if "project_path" in raw_data:
                project_path = raw_data["project_path"]
                self.log("TRANSFORM", f"Analizando proyecto en {project_path}")

                analyzer = ProjectAnalyzer(project_path)
                analysis_results = analyzer.analyze()
                transformed_data["analysis_results"] = analysis_results

                # Enriquecer con IA si está disponible
                if self.ai_enhancer.is_available():
                    self.log("TRANSFORM", "Enriqueciendo análisis con IA")
                    analysis_results = self.ai_enhancer.enhance_documentation(analysis_results)
                    transformed_data["analysis_results"] = analysis_results

                # Minería de patrones
                self.log("TRANSFORM", "Aplicando minería de patrones")
                mining_results = self.ai_enhancer.mine_code_patterns(analysis_results)
                transformed_data["mining_results"] = mining_results

            # Si son datos tabulares (CSV/JSON), aplicar limpieza
            elif raw_data.get("data") and isinstance(raw_data["data"], list):
                self.log("TRANSFORM", "Aplicando limpieza de datos")

                data = raw_data["data"]

                # Eliminar duplicados
                data = self.data_cleaner.remove_duplicates(data)

                # Rellenar valores faltantes
                data = self.data_cleaner.fill_missing_values(data, strategy="mean")

                # Normalizar strings
                data = self.data_cleaner.normalize_strings(data)

                transformed_data["data"] = data
                transformed_data["cleaning_report"] = self.data_cleaner.get_cleaning_report()

                # Detectar outliers si hay columnas numéricas
                if data and isinstance(data[0], dict):
                    for column in data[0].keys():
                        if any(isinstance(d.get(column), (int, float)) for d in data):
                            outliers = self.data_cleaner.detect_outliers(data, column, method="iqr")
                            if outliers["count"] > 0:
                                self.log("TRANSFORM", f"Outliers detectados en columna {column}: {outliers['count']}")

            # Aplicar reglas personalizadas si se proporcionan
            if rules:
                self.log("TRANSFORM", f"Aplicando {len(rules)} reglas de transformación")
                for rule in rules:
                    self._apply_rule(transformed_data, rule)

            self.log("TRANSFORM", "Transformación completada exitosamente")
            return transformed_data

        except Exception as e:
            self.log("TRANSFORM", f"Error en transformación: {str(e)}")
            transformed_data["error"] = str(e)
            return transformed_data

    def _apply_rule(self, data: Dict[str, Any], rule: Dict[str, Any]):
        """Aplica una regla de transformación específica."""
        rule_type = rule.get("type")

        if rule_type == "filter":
            # Filtrar datos basado en condición
            field = rule.get("field")
            operator = rule.get("operator")
            value = rule.get("value")

            if data.get("data") and isinstance(data["data"], list):
                if operator == "equals":
                    data["data"] = [d for d in data["data"] if d.get(field) == value]
                elif operator == "contains":
                    data["data"] = [d for d in data["data"] if value in str(d.get(field, ""))]
                elif operator == "greater_than":
                    data["data"] = [d for d in data["data"] if d.get(field, 0) > value]

        elif rule_type == "rename":
            # Renombrar campos
            old_name = rule.get("old_name")
            new_name = rule.get("new_name")

            if data.get("data") and isinstance(data["data"], list):
                for item in data["data"]:
                    if old_name in item:
                        item[new_name] = item.pop(old_name)

        elif rule_type == "add_field":
            # Agregar campo calculado
            field_name = rule.get("field_name")
            expression = rule.get("expression")

            if data.get("data") and isinstance(data["data"], list):
                for item in data["data"]:
                    if expression == "timestamp":
                        item[field_name] = datetime.utcnow().isoformat()
                    elif expression == "row_number":
                        item[field_name] = data["data"].index(item) + 1

    def load(self, transformed_data: Dict[str, Any], target: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Carga los datos transformados al destino especificado.

        Tipos de carga:
        - 'mongodb': base de datos (ya tienes db.py)
        - 'html': exportación (ya tienes exporter.py)
        - 'pdf': exportación (ya tienes exporter.py)

        Args:
            transformed_data: Datos transformados
            target: Tipo de destino
            output_path: Ruta de salida (para archivos)

        Returns:
            Diccionario con resultado de la carga
        """
        self.log("LOAD", f"Iniciando carga a destino: {target}")

        load_result = {
            "loaded_at": datetime.utcnow().isoformat(),
            "target": target,
            "output_path": output_path,
            "success": False
        }

        try:
            if target == "html":
                if not transformed_data.get("analysis_results"):
                    raise ValueError("Se requieren analysis_results para generar HTML")

                doc_generator = DocGenerator(transformed_data["analysis_results"])
                docs = doc_generator.generate()

                if output_path:
                    output_file = Path(output_path)
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(docs["full_markdown"], encoding='utf-8')
                    load_result["output_path"] = str(output_file)

                load_result["success"] = True
                load_result["documentation"] = docs

            elif target == "pdf":
                if not transformed_data.get("analysis_results"):
                    raise ValueError("Se requieren analysis_results para generar PDF")

                doc_generator = DocGenerator(transformed_data["analysis_results"])
                docs = doc_generator.generate()

                # Usar DocumentExporter para generar PDF
                # DocumentExporter requiere project y analysis_result
                project = {"_id": "etl_export", "name": "ETL Pipeline Export"}
                analysis_result = {"results": transformed_data["analysis_results"], "documentation": docs}

                exporter = DocumentExporter(project, analysis_result)
                pdf_path = exporter.to_pdf()

                load_result["output_path"] = pdf_path
                load_result["success"] = True

            elif target == "json":
                if output_path:
                    output_file = Path(output_path)
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(json.dumps(transformed_data, indent=2, default=str), encoding='utf-8')
                    load_result["output_path"] = str(output_file)
                load_result["success"] = True

            elif target == "mongodb":
                # Integración con db.py (si existe)
                try:
                    from services.db import save_analysis
                    if transformed_data.get("analysis_results"):
                        save_analysis(transformed_data["analysis_results"])
                        load_result["success"] = True
                        load_result["message"] = "Datos guardados en MongoDB"
                except ImportError:
                    self.log("LOAD", "Módulo db.py no disponible, skipping MongoDB")
                    load_result["message"] = "MongoDB no disponible"

            else:
                raise ValueError(f"Tipo de destino no soportado: {target}")

            self.log("LOAD", f"Carga completada exitosamente a {target}")
            return load_result

        except Exception as e:
            self.log("LOAD", f"Error en carga: {str(e)}")
            load_result["error"] = str(e)
            return load_result

    def run_pipeline(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo E → T → L.

        Args:
            config: Configuración del pipeline con:
                - extract: {source_type, source_path, project_id}
                - transform: {rules}
                - load: {target, output_path}

        Returns:
            Diccionario con resultados completos del pipeline
        """
        self.log("PIPELINE", "Iniciando pipeline ETL completo")

        pipeline_result = {
            "started_at": datetime.utcnow().isoformat(),
            "config": config,
            "extract": None,
            "transform": None,
            "load": None,
            "completed_at": None,
            "success": False,
            "log": []
        }

        try:
            # EXTRACT
            extract_config = config.get("extract", {})
            extract_result = self.extract(
                source_type=extract_config.get("source_type"),
                source_path=extract_config.get("source_path"),
                project_id=extract_config.get("project_id")
            )
            pipeline_result["extract"] = extract_result

            if extract_result.get("error"):
                raise Exception(f"Error en Extract: {extract_result['error']}")

            # TRANSFORM
            transform_config = config.get("transform", {})
            transform_result = self.transform(
                raw_data=extract_result,
                rules=transform_config.get("rules")
            )
            pipeline_result["transform"] = transform_result

            if transform_result.get("error"):
                raise Exception(f"Error en Transform: {transform_result['error']}")

            # LOAD
            load_config = config.get("load", {})
            load_result = self.load(
                transformed_data=transform_result,
                target=load_config.get("target"),
                output_path=load_config.get("output_path")
            )
            pipeline_result["load"] = load_result

            if not load_result.get("success"):
                raise Exception(f"Error en Load: {load_result.get('error')}")

            pipeline_result["success"] = True
            pipeline_result["completed_at"] = datetime.utcnow().isoformat()
            pipeline_result["log"] = self.pipeline_log

            self.log("PIPELINE", "Pipeline ETL completado exitosamente")
            return pipeline_result

        except Exception as e:
            self.log("PIPELINE", f"Error en pipeline: {str(e)}")
            pipeline_result["error"] = str(e)
            pipeline_result["completed_at"] = datetime.utcnow().isoformat()
            pipeline_result["log"] = self.pipeline_log
            return pipeline_result

    def get_pipeline_diagram(self) -> str:
        """
        Genera un diagrama PlantUML del pipeline ETL.
        """
        puml = """@startuml
skinparam backgroundColor #FEFEFE
title Pipeline ETL - AutoDocs AI

package "Extract" {
  [ZIP Source] as zip
  [GitHub Repo] as github
  [CSV Dataset] as csv
  [JSON Data] as json
  [Directory] as dir
}

package "Transform" {
  [Data Cleaner] as cleaner
  [AI Enhancer] as ai
  [Pattern Mining] as mining
  [Rules Engine] as rules
}

package "Load" {
  [HTML Export] as html
  [PDF Export] as pdf
  [MongoDB] as mongo
  [JSON File] as json_file
}

zip --> cleaner
github --> cleaner
csv --> cleaner
json --> cleaner
dir --> cleaner

cleaner --> ai
ai --> mining
mining --> rules

rules --> html
rules --> pdf
rules --> mongo
rules --> json_file

@enduml"""

        return puml
