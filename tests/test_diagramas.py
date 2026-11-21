"""
tests/test_diagramas.py

Diagramas de la documentación: siempre deben salir como imagen incrustada, no solo como enlace.
- services/diagram_fallback.py (dibujo local con Pillow)
- cadena local -> remoto -> dibujo propio en DocGenerator
- conversión de las imágenes de diagrama para el exportador (Markdown -> HTML)

Ejecutar con: python -m pytest tests/test_diagramas.py -v
"""

import base64
import shutil
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services import diagram_fallback
from services.doc_generator import DocGenerator
from services.exporter import DocumentExporter

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CLASS_PUML = """@startuml
skinparam classAttributeIconSize 0
class "Usuario" as cls_1 <<Entity>> {
  +guardar()
  +borrar()
}
class "Pedido" as cls_2 {
}
cls_2 --> cls_1 : FK
@enduml"""

INFRA_PUML = """@startuml
skinparam componentStyle rectangle
package "Backend" {
  [Rutas] as routes
  [Logica] as logic
  routes --> logic
}
database "BD" as db
logic --> db
@enduml"""

USECASE_PUML = """@startuml
left to right direction
actor "Usuario" as user
rectangle "Sistema" {
  usecase "GET /api/x" as uc_1
  user --> uc_1
}
@enduml"""


@pytest.fixture(autouse=True)
def mock_ai():
    with patch("services.doc_generator.AIEnhancer") as MockAI:
        MockAI.return_value.is_available.return_value = False
        yield


@pytest.fixture
def gen():
    return DocGenerator({"primary_language": "Python"})


# ─── Lectura del PlantUML ────────────────────────────────────────────────────

class TestParse:
    def test_clase_con_estereotipo_miembros_y_relacion(self):
        title, nodes, edges, containers = diagram_fallback.parse(CLASS_PUML)
        assert nodes["cls_1"].label == "Usuario"
        assert nodes["cls_1"].stereo == "Entity"
        assert nodes["cls_1"].members == ["guardar()", "borrar()"]
        assert nodes["cls_2"].members == []
        assert edges == [("cls_2", "cls_1", "FK")]

    def test_contenedores_y_componentes(self):
        _, nodes, edges, containers = diagram_fallback.parse(INFRA_PUML)
        assert containers == [("Backend", ["routes", "logic"])]
        assert nodes["db"].kind == "database"
        assert nodes["routes"].kind == "component"
        assert ("routes", "logic", "") in edges

    def test_actor_y_caso_de_uso(self):
        _, nodes, _, containers = diagram_fallback.parse(USECASE_PUML)
        assert nodes["user"].kind == "actor"
        assert nodes["uc_1"].kind == "usecase"
        assert containers[0][0] == "Sistema"

    def test_titulo_y_etiqueta_sin_dos_puntos(self):
        code = '@startuml\ntitle Mi diagrama\n[A] as a\n[B] as b\na --> b  FK\n@enduml'
        title, _, edges, _ = diagram_fallback.parse(code)
        assert title == "Mi diagrama"
        assert edges == [("a", "b", "FK")]

    def test_flecha_a_elemento_no_declarado_lo_crea(self):
        _, nodes, _, _ = diagram_fallback.parse("@startuml\n[A] as a\na --> fantasma\n@enduml")
        assert "fantasma" in nodes


# ─── Dibujo ──────────────────────────────────────────────────────────────────

class TestRenderPng:
    @pytest.mark.parametrize("code", [CLASS_PUML, INFRA_PUML, USECASE_PUML])
    def test_genera_png_valido(self, code):
        png = diagram_fallback.render_png(code)
        assert png and png.startswith(PNG_MAGIC) and len(png) > 500

    def test_vacio_devuelve_none(self):
        assert diagram_fallback.render_png("") is None
        assert diagram_fallback.render_png("@startuml\n@enduml") is None

    def test_demasiados_elementos_devuelve_none(self):
        code = "@startuml\n" + "".join(f"[N{i}] as n{i}\n" for i in range(diagram_fallback.MAX_NODES + 1)) + "@enduml"
        assert diagram_fallback.render_png(code) is None

    def test_ciclos_no_cuelgan(self):
        code = "@startuml\n[A] as a\n[B] as b\n[C] as c\na --> b\nb --> c\nc --> a\n@enduml"
        assert diagram_fallback.render_png(code).startswith(PNG_MAGIC)

    def test_muchas_clases_sin_relaciones_quedan_en_cuadricula(self):
        from PIL import Image
        import io
        code = "@startuml\n" + "".join(f'class "C{i}" as c{i} {{\n  +m()\n}}\n' for i in range(15)) + "@enduml"
        img = Image.open(io.BytesIO(diagram_fallback.render_png(code)))
        assert 0.6 < img.width / img.height < 2.5  # ni una columna larga ni una fila interminable

    def test_sin_pillow_devuelve_none(self):
        with patch.object(diagram_fallback, "Image", None):
            assert diagram_fallback.render_png(CLASS_PUML) is None


# ─── Cadena de respaldo en DocGenerator ──────────────────────────────────────

class TestOfflineOrLink:
    def test_devuelve_imagen_incrustada(self, gen):
        uri = gen._offline_or_link(CLASS_PUML)
        assert uri.startswith("data:image/png;base64,")
        assert base64.b64decode(uri.split(",", 1)[1]).startswith(PNG_MAGIC)

    def test_si_no_se_puede_dibujar_devuelve_el_enlace(self, gen):
        with patch.object(diagram_fallback, "render_png", return_value=None):
            assert gen._offline_or_link(CLASS_PUML).startswith("https://www.planttext.com/plantuml/png/")


class TestCadenaCompleta:
    def test_sin_plantuml_local_ni_red_el_diagrama_sale_como_imagen(self, gen, tmp_path):
        with patch.object(DocGenerator, "_get_plantuml_command", return_value=[]), \
                patch.object(DocGenerator, "_fetch_plantuml_image", return_value=None):
            uri = gen._generate_plantuml_diagram(CLASS_PUML, str(tmp_path))
        assert uri.startswith("data:image/png;base64,")

    def test_bloque_de_diagrama_lleva_img_y_enlace_de_edicion(self, gen, tmp_path):
        with patch.object(DocGenerator, "_get_plantuml_command", return_value=[]), \
                patch.object(DocGenerator, "_fetch_plantuml_image", return_value=None), \
                patch.object(DocGenerator, "_generate_plantuml_diagram",
                             wraps=lambda code, *a: gen._offline_or_link(code)):
            block = gen._render_diagram_block("Diagrama de Clases", CLASS_PUML)
        assert '<img src="data:image/png;base64,' in block
        assert 'alt="Diagrama de Clases"' in block
        assert "planttext.com/?text=" in block

    def test_sin_graphviz_usa_el_motor_interno_smetana(self, gen, tmp_path):
        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"jar")
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["puml"] = Path(cmd[4]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, "", "")

        with patch.dict("os.environ", {"PLANTUML_JAR_PATH": str(jar)}), \
                patch.object(DocGenerator, "_graphviz_available", return_value=False), \
                patch("services.doc_generator.subprocess.run", side_effect=fake_run), \
                patch.object(DocGenerator, "_fetch_plantuml_image", return_value=None):
            gen._generate_plantuml_diagram(CLASS_PUML, str(tmp_path))
        assert seen["puml"].startswith("@startuml\n!pragma layout smetana")

    def test_con_graphviz_no_se_cambia_el_motor(self, gen, tmp_path):
        jar = tmp_path / "plantuml.jar"
        jar.write_bytes(b"jar")
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["puml"] = Path(cmd[4]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, "", "")

        with patch.dict("os.environ", {"PLANTUML_JAR_PATH": str(jar)}), \
                patch.object(DocGenerator, "_graphviz_available", return_value=True), \
                patch("services.doc_generator.subprocess.run", side_effect=fake_run), \
                patch.object(DocGenerator, "_fetch_plantuml_image", return_value=None):
            gen._generate_plantuml_diagram(CLASS_PUML, str(tmp_path))
        assert "smetana" not in seen["puml"]


class TestCorteRemoto:
    def test_sin_red_solo_se_espera_una_vez(self, gen, tmp_path):
        with patch("services.doc_generator.urllib.request.urlopen",
                   side_effect=urllib.error.URLError("sin red")) as urlopen:
            assert gen._fetch_plantuml_image(CLASS_PUML, tmp_path / "a") is None
            intentos = urlopen.call_count
            assert gen._remote_diagrams_down is True
            assert gen._fetch_plantuml_image(INFRA_PUML, tmp_path / "b") is None
            assert urlopen.call_count == intentos  # el segundo diagrama ya no reintenta

    def test_servidor_que_responde_con_error_no_activa_el_corte(self, gen, tmp_path):
        error = urllib.error.HTTPError("http://x", 429, "Too Many", {}, None)
        with patch("services.doc_generator.urllib.request.urlopen", side_effect=error):
            assert gen._fetch_plantuml_image(CLASS_PUML, tmp_path / "a") is None
        assert getattr(gen, "_remote_diagrams_down", False) is False


# ─── Conversión para el exportador ───────────────────────────────────────────

IMG_LINE = '<img src="data:image/png;base64,AAAA" alt="Diagrama de Clases">'


class TestImgAMarkdown:
    def test_convierte_imagen_de_diagrama(self):
        out = DocumentExporter._standalone_img_to_markdown(f"Antes\n\n{IMG_LINE}\n\nDespués")
        assert "![Diagrama de Clases](data:image/png;base64,AAAA)" in out
        assert "<img" not in out

    def test_no_toca_imagenes_dentro_de_otro_elemento(self):
        barra = '<div style="margin:1px"><img src="data:image/png;base64,BBBB" alt="Nivel"></div>'
        assert DocumentExporter._standalone_img_to_markdown(barra) == barra

    def test_alt_con_corchetes_no_rompe_la_sintaxis(self):
        out = DocumentExporter._standalone_img_to_markdown('<img src="x.png" alt="A [b]">')
        assert out == "![A (b)](x.png)"


class TestNodeConservaLaImagen:
    @pytest.fixture
    def exporter(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.exporter.EXPORT_BASE", tmp_path)
        return DocumentExporter({"_id": "p", "name": "Demo"}, {"results": {}, "documentation": {}})

    def test_html_final_trae_la_imagen_incrustada(self, exporter):
        if not (shutil.which("node") and (Path(__file__).resolve().parents[1] / "node_modules" / "remark").exists()):
            pytest.skip("Node o node_modules no disponibles en este entorno")
        try:
            html = exporter._render_markdown_with_node(f"### 2.6 Diagrama de Clases\n\n{IMG_LINE}\n")
        except RuntimeError:
            pytest.skip("Esta versión de Node no puede cargar remark")
        assert '<img src="data:image/png;base64,AAAA"' in html

    def test_script_html_crudo_sigue_bloqueado(self, exporter):
        if not (shutil.which("node") and (Path(__file__).resolve().parents[1] / "node_modules" / "remark").exists()):
            pytest.skip("Node o node_modules no disponibles en este entorno")
        try:
            html = exporter._render_markdown_with_node("<script>alert(1)</script>\n\n[x](javascript:alert(1))\n")
        except RuntimeError:
            pytest.skip("Esta versión de Node no puede cargar remark")
        assert "<script" not in html and "javascript:" not in html

    def test_to_html_con_conversor_alternativo_conserva_el_diagrama(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.exporter.EXPORT_BASE", tmp_path)
        md = f"## 2. Arquitectura\n\n### 2.6 Diagrama de Clases\n\n{IMG_LINE}\n\nTexto\n"
        exp = DocumentExporter({"_id": "p", "name": "Demo"}, {"results": {}, "documentation": {"full_markdown": md}})
        with patch.object(DocumentExporter, "_render_markdown_with_node", side_effect=RuntimeError("sin node")):
            html = exp.to_html()
        assert 'src="data:image/png;base64,AAAA"' in html
