"""
tests/test_doc_formato.py

Formato de la documentación generada:
- descripciones largas y claras,
- título + descripción + tabla en la misma página (agrupación en el HTML),
- título de sección junto a su subtítulo.

Ejecutar con: python -m pytest tests/test_doc_formato.py -v
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from services import ai_enhancer as ai_mod
from services.ai_enhancer import AIEnhancer, LONG_DESCRIPTION_STYLE, LONG_DESCRIPTION_TOKENS
from services.doc_generator import DocGenerator
from services.exporter import DocumentExporter


@pytest.fixture(autouse=True)
def mock_ai_and_plantuml():
    with patch("services.doc_generator.AIEnhancer") as MockAI, \
            patch.object(DocGenerator, "_generate_plantuml_diagram", return_value=""):
        inst = MagicMock()
        inst.is_available.return_value = False
        MockAI.return_value = inst
        yield


@pytest.fixture
def gen():
    return DocGenerator({"primary_language": "Python"})


@pytest.fixture
def exporter(tmp_path, monkeypatch):
    monkeypatch.setattr("services.exporter.EXPORT_BASE", tmp_path)
    return DocumentExporter({"_id": "p", "name": "Demo"}, {"results": {}, "documentation": {}})


def _model(name="Llave", nfields=4, nmethods=2):
    return {
        "name": name, "file": f"models/{name.lower()}.py", "line": 10, "bases": ["Model"],
        "fields": [f"campo_{i}" for i in range(nfields)],
        "methods": [f"metodo_{i}" for i in range(nmethods)],
    }


# ─── Descripciones largas ────────────────────────────────────────────────────

class TestLongDescription:
    def test_respeta_descripcion_ya_extensa(self, gen):
        largo = " ".join(["palabra"] * 80)
        assert gen._long_description("model", _model(), largo) == largo

    def test_completa_descripcion_corta_real_sin_perderla(self, gen):
        out = gen._long_description("class", _model(), "Descripción generada por IA")
        assert out.startswith("Descripción generada por IA.")
        assert "**Llave**" in out
        assert len(out.split()) >= 50

    def test_reemplaza_texto_de_relleno(self, gen):
        out = gen._long_description("model", _model(), "Modelo Llave")
        assert not out.startswith("Modelo Llave")
        assert "El modelo **Llave**" in out

    def test_sin_base_genera_explicacion_larga_y_clara(self, gen):
        out = gen._long_description("model", _model(), "")
        assert len(out.split()) >= 50
        assert "models/llave.py" in out
        assert "campo_0" in out and "metodo_0()" in out

    def test_explicacion_en_ingles(self):
        g = DocGenerator({"primary_language": "Python"}, lang="en")
        out = g._long_description("model", _model(), "")
        assert "The **Llave** model" in out
        assert "It stores 4 fields" in out

    @pytest.mark.parametrize("kind,item", [
        ("class", _model("Servicio")),
        ("function", {"name": "calcular", "file": "a.py", "params": ["x", "y"], "complexity": 12, "is_async": True}),
        ("endpoint", {"method": "POST", "path": "/api/x", "file": "app.py", "framework": "Flask"}),
    ])
    def test_todos_los_tipos_generan_texto(self, gen, kind, item):
        assert len(gen._long_description(kind, item, "").split()) >= 30

    @pytest.mark.parametrize("texto", ["Modelo Llave", "Clase X", "Endpoint GET /api/x", "Función f",
                                       "Modelo de datos que representa la entidad X en el sistema."])
    def test_detecta_rellenos(self, texto):
        assert DocGenerator._is_placeholder_description(texto)

    @pytest.mark.parametrize("texto", ["Descripción generada por IA", "Guarda las llaves de acceso del usuario."])
    def test_no_toma_descripciones_reales_como_relleno(self, texto):
        assert not DocGenerator._is_placeholder_description(texto)

    def test_varios_parrafos_quedan_en_una_sola_cita(self, gen):
        quote = gen._description_quote("Primer párrafo.\n\nSegundo párrafo.")
        assert quote.startswith("> **Descripción:** Primer párrafo.")
        assert "\n>\n> Segundo párrafo." in quote
        assert all(line.startswith(">") for line in quote.strip().splitlines())


class TestMarkdownGenerado:
    def test_detalle_de_modelos_sin_div_y_con_descripcion_larga(self, gen):
        gen.r["models"] = [_model("Llave")]
        md = gen._data_models()
        assert "<div" not in md
        assert "#### `Llave`" in md
        desc = re.search(r"> \*\*Descripción:\*\*(.*?)\n\n\|", md, flags=re.DOTALL).group(1)
        assert len(desc.split()) >= 50

    def test_tablas_de_endpoint_separadas_por_linea_en_blanco(self, gen):
        gen.r["endpoints"] = [{"method": "GET", "path": "/api/x", "file": "app.py"}]
        md = gen._api_section()
        assert "\n\n| Código" in md or "\n\n| Code" in md


class TestPromptsDeIA:
    @pytest.mark.parametrize("metodo,arg", [
        ("enhance_function_description", {"name": "f", "params": ["a"]}),
        ("enhance_class_description", {"name": "C", "methods": ["m"], "bases": []}),
        ("enhance_endpoint_description", {"method": "GET", "path": "/x"}),
        ("enhance_model_description", {"name": "M", "fields": [], "methods": []}),
    ])
    def test_piden_descripciones_largas(self, metodo, arg):
        enh = AIEnhancer()
        with patch.object(AIEnhancer, "is_available", return_value=True), \
                patch.object(AIEnhancer, "_call_ai", return_value="ok") as call:
            getattr(enh, metodo)(arg)
        _system, user_prompt = call.call_args.args[:2]
        assert "entre 120 y 220 palabras" in user_prompt
        assert "máximo 120 palabras" not in user_prompt and "máximo 150 palabras" not in user_prompt
        assert call.call_args.kwargs["max_tokens"] == LONG_DESCRIPTION_TOKENS >= 600
        assert LONG_DESCRIPTION_STYLE.split(".")[0] in user_prompt


# ─── Agrupación en el HTML (título + descripción + tabla) ────────────────────

TABLE_SMALL = "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table>"


def _big_table(rows):
    body = "".join(f"<tr><td>c{i}</td><td>x</td></tr>" for i in range(rows))
    return f"<table><thead><tr><th>Campo</th><th>Tipo</th></tr></thead><tbody>{body}</tbody></table>"


class TestKeepBlocksTogether:
    def test_titulo_descripcion_y_tabla_quedan_en_un_bloque(self, exporter):
        html = f"<h4><code>Llave</code></h4>\n<blockquote><p>desc</p></blockquote>\n{TABLE_SMALL}\n<hr>\n<h4>Otra</h4>"
        out = exporter._keep_blocks_together(html)
        assert out.startswith(f'<div class="keep-block"><h4><code>Llave</code></h4><blockquote><p>desc</p></blockquote>{TABLE_SMALL}</div>')

    def test_elimina_hr_final_del_bloque(self, exporter):
        html = f"<h4>A</h4><blockquote><p>d</p></blockquote>{TABLE_SMALL}<hr><h4>B</h4>"
        out = exporter._keep_blocks_together(html)
        assert "<hr" not in out
        assert out.count('class="keep-block"') == 2 or '<h4>B</h4>' in out

    def test_etiqueta_se_queda_con_su_tabla(self, exporter):
        html = (f"<h4>M</h4><blockquote><p>d</p></blockquote>{_big_table(8)}"
                f"<p><strong>Métodos del Modelo:</strong></p>{_big_table(6)}<p><strong>Otra:</strong></p>{_big_table(40)}")
        out = exporter._keep_blocks_together(html)
        assert '<div class="keep-block"><p><strong>Métodos del Modelo:</strong></p>' in out
        # tabla larga: la etiqueta no queda sola al final de página, pero la tabla puede partirse
        assert '<p class="keep-next"><strong>Otra:</strong></p>' in out

    def test_bloque_largo_solo_agrupa_cabecera(self, exporter):
        html = f"<h4>M</h4><blockquote><p>d</p></blockquote>{_big_table(10)}{_big_table(30)}"
        out = exporter._keep_blocks_together(html)
        assert out.count('<div class="keep-block">') == 1
        assert out.startswith('<div class="keep-block"><h4>M</h4>')
        assert _big_table(30) in out and out.index(_big_table(30)) > out.index("</div>")

    def test_no_agrupa_tablas_anchas(self, exporter):
        ancha = "<table><thead><tr>" + "".join(f"<th>c{i}</th>" for i in range(6)) + "</tr></thead></table>"
        out = exporter._keep_blocks_together(f"<h4>M</h4>{ancha}")
        assert "keep-block" not in out

    def test_titulo_sin_contenido_agrupable_queda_igual(self, exporter):
        assert exporter._keep_blocks_together("<h4>Solo</h4><div>x</div>") == "<h4>Solo</h4><div>x</div>"

    def test_pre_no_se_mete_en_bloque_corto(self, exporter):
        html = f"<h4>F</h4><blockquote><p>d</p></blockquote><pre><code>x</code></pre>{TABLE_SMALL}"
        out = exporter._keep_blocks_together(html)
        assert "<pre>" in out  # el código puede fluir; solo se agrupa la cabecera
        assert out.startswith('<div class="keep-block"><h4>F</h4>')


class TestHeadingChain:
    def test_une_seccion_y_subtitulo(self, exporter):
        html = '<h2 id="sec3">3. Documentación Técnica de Código</h2>\n<h3 id="sec4">3.1 Guía</h3>\n<pre>x</pre>'
        out = exporter._group_heading_chain(html)
        assert out.startswith('<div class="keep-head"><h2 id="sec3">3. Documentación Técnica de Código</h2>')
        assert '<h3 id="sec4">3.1 Guía</h3></div>' in out

    def test_no_toca_h3_sin_titulo_previo(self, exporter):
        html = "<p>x</p><h3>3.1</h3>"
        assert exporter._group_heading_chain(html) == html


class TestHtmlFinal:
    def test_to_html_incluye_agrupaciones_y_estilos(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.exporter.EXPORT_BASE", tmp_path)
        md = ("## 3. Documentación Técnica de Código\n\n### 3.1 Guía\n\nTexto\n\n"
              "#### `Llave`\n\n> **Descripción:** algo\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n---\n")
        exp = DocumentExporter({"_id": "p", "name": "Demo"}, {"results": {}, "documentation": {"full_markdown": md}})
        with patch.object(DocumentExporter, "_render_markdown_with_node", side_effect=RuntimeError("sin node")):
            html = exp.to_html()
        assert '<div class="keep-head">' in html
        assert '<div class="keep-block">' in html
        assert ".keep-block" in html and "break-inside: avoid" in html
        assert "h4 code" in html
