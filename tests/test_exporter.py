"""
tests/test_exporter.py

Tests unitarios para services/exporter.py
Ejecutar con: python -m pytest tests/test_exporter.py -v
"""

import base64
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from services.exporter import DocumentExporter, EXPORT_BASE


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_export_base(tmp_path, monkeypatch):
    """
    Redirige EXPORT_BASE a un directorio temporal para no ensuciar ./exports.
    """
    fake_base = tmp_path / "exports"
    fake_base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("services.exporter.EXPORT_BASE", fake_base)
    yield fake_base


@pytest.fixture
def sample_project():
    return {
        "_id": "proj123abc",
        "name": "Mi Proyecto Demo",
    }


@pytest.fixture
def sample_analysis():
    return {
        "results": {
            "total_files": 12,
            "functions": [
                {"name": "f1", "file": "a.py", "docstring": "doc", "complexity": 2},
                {"name": "f2", "file": "b.py", "docstring": "", "complexity": 8},
            ],
            "classes": [
                {"name": "UserModel", "file": "m.py"},
            ],
            "endpoints": [
                {"method": "GET", "path": "/api/users"},
                {"method": "POST", "path": "/api/users"},
            ],
            "quality_score": 75,
        },
        "documentation": {
            "full_markdown": "# Título\n\nContenido de prueba\n\n## Sección 1\n\nTexto\n",
        },
    }


@pytest.fixture
def exporter(sample_project, sample_analysis):
    return DocumentExporter(sample_project, sample_analysis)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: __init__
# ─────────────────────────────────────────────────────────────────────────────

class TestInit:
    def test_guarda_project_y_results(self, exporter, sample_project, sample_analysis):
        assert exporter.project == sample_project
        assert exporter.results == sample_analysis["results"]
        assert exporter.docs == sample_analysis["documentation"]

    def test_crea_export_base(self, tmp_path, monkeypatch):
        fake_base = tmp_path / "no_existe"
        monkeypatch.setattr("services.exporter.EXPORT_BASE", fake_base)
        assert not fake_base.exists()
        DocumentExporter({"_id": "x", "name": "y"}, {"results": {}, "documentation": {}})
        assert fake_base.exists()

    def test_analysis_sin_results_ni_docs(self):
        exp = DocumentExporter({"_id": "x", "name": "y"}, {})
        assert exp.results == {}
        assert exp.docs == {}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_markdown
# ─────────────────────────────────────────────────────────────────────────────

class TestToMarkdown:
    def test_devuelve_markdown_existente(self, exporter):
        result = exporter.to_markdown()
        assert "# Título" in result
        assert "Contenido de prueba" in result

    def test_sin_documentacion_devuelve_placeholder(self, sample_project):
        exp = DocumentExporter(sample_project, {"results": {}, "documentation": {}})
        assert "Sin documentación generada" in exp.to_markdown()

    def test_documentation_sin_full_markdown(self, sample_project):
        exp = DocumentExporter(sample_project, {"results": {}, "documentation": {"otra": "x"}})
        assert "Sin documentación generada" in exp.to_markdown()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _markdown_table_to_html
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkdownTableToHtml:
    def test_tabla_simple(self, exporter):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
        result = exporter._markdown_table_to_html(md)
        assert '<table class="report-table">' in result
        assert "<th>A</th>" in result
        assert "<th>B</th>" in result
        assert "<td>1</td>" in result
        assert "<td>2</td>" in result
        assert "<td>3</td>" in result

    def test_texto_sin_tabla_no_cambia(self, exporter):
        md = "Solo texto\nsin tablas\n"
        result = exporter._markdown_table_to_html(md)
        assert result == md

    def test_tabla_con_separadores_alineados(self, exporter):
        md = "| Col1 | Col2 |\n| :--- | ---: |\n| a | b |"
        result = exporter._markdown_table_to_html(md)
        assert "<th>Col1</th>" in result
        assert "<td>a</td>" in result

    def test_tabla_con_filas_inconsistentes(self, exporter):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| solo-una-celda |"
        result = exporter._markdown_table_to_html(md)
        # La fila inconsistente se ignora
        assert "<td>1</td>" in result
        assert "solo-una-celda" not in result

    def test_tabla_vacia(self, exporter):
        md = "| A | B |\n| --- | --- |\n"
        result = exporter._markdown_table_to_html(md)
        assert "<table" in result
        assert "<tbody></tbody>" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _render_markdown_with_node
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderMarkdownWithNode:
    def test_script_no_existe_lanza_error(self, exporter, tmp_path, monkeypatch):
        # Forzar a que el script no exista
        with patch("services.exporter.Path") as MockPath:
            mock_script = MagicMock()
            mock_script.exists.return_value = False
            MockPath.return_value.resolve.return_value.parents = [None, MagicMock()]
            # Simplificamos: solo probamos que el flujo lance FileNotFoundError
            with patch.object(Path, "exists", return_value=False):
                with pytest.raises(FileNotFoundError):
                    exporter._render_markdown_with_node("test")

    @patch("services.exporter.subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_node_exitoso(self, mock_exists, mock_run, exporter):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="<p>HTML generado</p>",
            stderr="",
        )
        result = exporter._render_markdown_with_node("# Test")
        assert "<p>HTML generado</p>" in result

    @patch("services.exporter.subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_node_falla_lanza_error(self, mock_exists, mock_run, exporter):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error de node",
        )
        with pytest.raises(RuntimeError) as exc:
            exporter._render_markdown_with_node("test")
        assert "Node markdown conversion failed" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_html
# ─────────────────────────────────────────────────────────────────────────────

class TestToHtml:
    def test_html_basico(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node", return_value="<p>Contenido</p>"):
            html = exporter.to_html()
            assert "<!DOCTYPE html>" in html
            assert "Mi Proyecto Demo" in html
            assert "<p>Contenido</p>" in html

    def test_html_incluye_score(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exporter.to_html()
            assert "Score de Calidad: 75/100" in html

    def test_html_incluye_estadisticas(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exporter.to_html()
            assert "12" in html  # total_files
            assert "2" in html   # 2 funciones

    def test_html_incluye_tabla_de_contenidos(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node",
                          return_value="<h1>Título</h1><h2>Subsección</h2>"):
            html = exporter.to_html()
            assert "Tabla de Contenidos" in html
            assert 'class="toc-list"' in html

    def test_html_usa_fallback_markdown_library(self, exporter):
        # Si _render_markdown_with_node falla, debe intentar usar la librería `markdown`
        with patch.object(exporter, "_render_markdown_with_node",
                          side_effect=Exception("Node no disponible")):
            with patch("builtins.__import__", side_effect=ImportError("markdown no instalado")):
                html = exporter.to_html()
                # Debe funcionar igual con el fallback manual
                assert "<!DOCTYPE html>" in html

    def test_html_sin_markdown_no_falla(self, sample_project):
        exp = DocumentExporter(sample_project, {"results": {}, "documentation": {}})
        with patch.object(exp, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exp.to_html()
            assert "<!DOCTYPE html>" in html

    def test_html_score_bajo_color_rojo(self, sample_project):
        exp = DocumentExporter(sample_project, {
            "results": {"quality_score": 20},
            "documentation": {"full_markdown": "# Test"},
        })
        with patch.object(exp, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exp.to_html()
            assert "#ef4444" in html  # rojo

    def test_html_score_medio_color_naranja(self, sample_project):
        exp = DocumentExporter(sample_project, {
            "results": {"quality_score": 50},
            "documentation": {"full_markdown": "# Test"},
        })
        with patch.object(exp, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exp.to_html()
            assert "#f59e0b" in html  # naranja

    def test_html_score_alto_color_verde(self, sample_project):
        exp = DocumentExporter(sample_project, {
            "results": {"quality_score": 85},
            "documentation": {"full_markdown": "# Test"},
        })
        with patch.object(exp, "_render_markdown_with_node", return_value="<p>x</p>"):
            html = exp.to_html()
            assert "#10b981" in html  # verde

    def test_html_inyecta_ids_en_headings(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node",
                          return_value='<h1>Primero</h1><h2>Segundo</h2><h3>Tercero</h3>'):
            html = exporter.to_html()
            assert 'id="sec1"' in html
            assert 'id="sec2"' in html
            assert 'id="sec3"' in html

    def test_html_resuelve_imagenes_data_uri(self, exporter):
        # El markdown contiene una imagen ya en data URI
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        with patch.object(exporter, "_render_markdown_with_node",
                          return_value=f'<img src="{data_uri}" alt="test">'):
            html = exporter.to_html()
            # Debe mantener el data URI
            assert data_uri in html


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _is_valid_pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestIsValidPdf:
    def test_pdf_valido(self, exporter, tmp_path):
        pdf = tmp_path / "valid.pdf"
        content = b"%PDF-1.4\n" + b"x" * 100 + b"\n%%EOF"
        pdf.write_bytes(content)
        assert exporter._is_valid_pdf(pdf) is True

    def test_pdf_sin_header(self, exporter, tmp_path):
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"NOT A PDF\n" + b"x" * 100 + b"\n%%EOF")
        assert exporter._is_valid_pdf(pdf) is False

    def test_pdf_sin_eof(self, exporter, tmp_path):
        pdf = tmp_path / "bad.pdf"
        pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 100)
        assert exporter._is_valid_pdf(pdf) is False

    def test_pdf_no_existe(self, exporter, tmp_path):
        pdf = tmp_path / "no_existe.pdf"
        assert exporter._is_valid_pdf(pdf) is False

    def test_pdf_vacio(self, exporter, tmp_path):
        pdf = tmp_path / "vacio.pdf"
        pdf.write_bytes(b"")
        assert exporter._is_valid_pdf(pdf) is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestToPdf:
    def test_weasyprint_exitoso(self, exporter, tmp_path):
        def fake_write_pdf(path_str):
            Path(path_str).write_bytes(b"%PDF-1.4\n" + b"x" * 2000 + b"\n%%EOF")

        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.side_effect = fake_write_pdf

        with patch("weasyprint.HTML", return_value=mock_html_instance):
            with patch.object(exporter, "to_html", return_value="<html></html>"):
                result = exporter.to_pdf()
                assert result.endswith(".pdf")
                assert Path(result).exists()

    def test_weasyprint_falla_usa_reportlab(self, exporter):
        with patch("weasyprint.HTML", side_effect=Exception("WeasyPrint roto")):
            with patch.object(exporter, "_pdf_with_reportlab") as mock_rl:
                # Simular que ReportLab genera un PDF válido
                def fake_reportlab(path):
                    p = Path(path)
                    p.write_bytes(b"%PDF-1.4\n" + b"x" * 2000 + b"\n%%EOF")
                    return str(p)
                mock_rl.side_effect = fake_reportlab

                with patch.object(exporter, "to_html", return_value="<html></html>"):
                    result = exporter.to_pdf()
                    assert result.endswith(".pdf")

    def test_ambos_fallan_devuelve_html(self, exporter):
        with patch("weasyprint.HTML", side_effect=Exception("Weasy roto")):
            with patch.object(exporter, "_pdf_with_reportlab", side_effect=Exception("ReportLab roto")):
                with patch.object(exporter, "to_html", return_value="<html></html>"):
                    result = exporter.to_pdf()
                    assert result.endswith(".html")

    def test_weasyprint_genera_archivo_invalido(self, exporter):
        # WeasyPrint genera un archivo muy pequeño → no debe aceptarlo
        def fake_write_pdf(path_str):
            Path(path_str).write_bytes(b"%PDF")  # muy pequeño

        mock_html = MagicMock()
        mock_html.write_pdf.side_effect = fake_write_pdf

        with patch("weasyprint.HTML", return_value=mock_html):
            with patch.object(exporter, "_pdf_with_reportlab") as mock_rl:
                mock_rl.return_value = str(EXPORT_BASE / "fallback.pdf")
                with patch.object(exporter, "to_html", return_value="<html></html>"):
                    exporter.to_pdf()
                    # Debe haber intentado ReportLab después
                    mock_rl.assert_called_once()

    def test_escribe_tambien_html(self, exporter):
        with patch("weasyprint.HTML", side_effect=Exception("x")):
            with patch.object(exporter, "_pdf_with_reportlab", side_effect=Exception("y")):
                with patch.object(exporter, "to_html", return_value="<html>test</html>"):
                    result = exporter.to_pdf()
                    html_path = Path(result)
                    assert html_path.read_text() == "<html>test</html>"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _pdf_with_reportlab (integración básica)
# ─────────────────────────────────────────────────────────────────────────────

class TestPdfWithReportlab:
    def test_genera_pdf_valido(self, exporter, tmp_path):
        output = tmp_path / "test_rl.pdf"

        # Mockeamos to_markdown para tener contenido predecible
        with patch.object(exporter, "to_markdown",
                          return_value="# Título Principal\n\nContenido de prueba.\n"):
            result = exporter._pdf_with_reportlab(str(output))

        assert Path(result).exists()
        assert Path(result).stat().st_size > 1000
        # Verificar header PDF
        with open(result, "rb") as f:
            assert f.read(5).startswith(b"%PDF")

    def test_pdf_con_markdown_vacio(self, exporter, tmp_path):
        output = tmp_path / "empty.pdf"
        with patch.object(exporter, "to_markdown", return_value=""):
            result = exporter._pdf_with_reportlab(str(output))
        assert Path(result).exists()

    def test_pdf_con_tabla_markdown(self, exporter, tmp_path):
        output = tmp_path / "table.pdf"
        md = "# Título\n\n| Col1 | Col2 |\n| --- | --- |\n| a | b |\n| c | d |\n"
        with patch.object(exporter, "to_markdown", return_value=md):
            result = exporter._pdf_with_reportlab(str(output))
        assert Path(result).exists()

    def test_pdf_con_bloque_de_codigo(self, exporter, tmp_path):
        output = tmp_path / "code.pdf"
        md = "# Título\n\n```python\ndef foo():\n    return 42\n```\n"
        with patch.object(exporter, "to_markdown", return_value=md):
            result = exporter._pdf_with_reportlab(str(output))
        assert Path(result).exists()

    def test_pdf_con_imagen_data_uri(self, exporter, tmp_path):
        output = tmp_path / "img.pdf"
        # PNG 1x1 mínimo en base64
        png_data = base64.b64encode(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        ).decode()
        md = f"# Título\n\n<img src=\"data:image/png;base64,{png_data}\">\n"
        with patch.object(exporter, "to_markdown", return_value=md):
            result = exporter._pdf_with_reportlab(str(output))
        assert Path(result).exists()

    def test_pdf_con_quote_y_listas(self, exporter, tmp_path):
        output = tmp_path / "misc.pdf"
        md = "# Título\n\n> Una cita importante\n\n- item 1\n- item 2\n\n---\n\nFin\n"
        with patch.object(exporter, "to_markdown", return_value=md):
            result = exporter._pdf_with_reportlab(str(output))
        assert Path(result).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Tests de integración
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    def test_flujo_completo_a_html(self, exporter):
        with patch.object(exporter, "_render_markdown_with_node", return_value="<p>HTML</p>"):
            html = exporter.to_html()
            assert "<!DOCTYPE html>" in html
            assert "</html>" in html
            assert "Mi Proyecto Demo" in html

    def test_flujo_completo_a_pdf(self, exporter):
        def fake_write_pdf(path_str):
            Path(path_str).write_bytes(b"%PDF-1.4\n" + b"x" * 2000 + b"\n%%EOF")

        mock_html = MagicMock()
        mock_html.write_pdf.side_effect = fake_write_pdf

        with patch("weasyprint.HTML", return_value=mock_html):
            with patch.object(exporter, "to_html", return_value="<html></html>"):
                result = exporter.to_pdf()
                assert Path(result).exists()
                assert Path(result).suffix == ".pdf"