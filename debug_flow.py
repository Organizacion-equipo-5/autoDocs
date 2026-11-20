import sys, os, tempfile, traceback
from pathlib import Path

sys.path.insert(0, '.')
from services.analyzer import ProjectAnalyzer
from services.doc_generator import DocGenerator
from services.exporter import DocumentExporter
import services.exporter as exp_mod

try:
    print("1. Analizando proyecto...")
    proj_path = Path("uploads/fd2929d0-0a99-4417-9f16-207fef04ba0b/proyecto_clase_python")
    analyzer = ProjectAnalyzer(str(proj_path.resolve()))
    results = analyzer.analyze()
    print("-> Análisis completo. Endpoints:", len(results.get('endpoints', [])), "Clases:", len(results.get('classes', [])))

    print("2. Creando DocGenerator...")
    doc_gen = DocGenerator(results, lang='es')
    print("3. Generando documentacion...")
    docs = doc_gen.generate()
    print("-> Documentación generada! Longitud full_markdown:", len(docs.get('full_markdown', '')))

    print("4. Exportando a PDF...")
    with tempfile.TemporaryDirectory() as td:
        exp_mod.EXPORT_BASE = Path(td)
        exporter = DocumentExporter({'_id': 'test_debug', 'name': 'ProyectoClase'}, {'results': results, 'documentation': docs})
        pdf_path = exporter.to_pdf()
        print("-> to_pdf completado:", pdf_path)
        if Path(pdf_path).exists():
            print("-> PDF Existe y tiene:", Path(pdf_path).stat().st_size, "bytes")
except Exception as e:
    print("EXCEPCION CAPTURADA:", e)
    traceback.print_exc()
