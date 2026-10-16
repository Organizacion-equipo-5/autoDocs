from pathlib import Path
from datetime import datetime
import html as _html
import io
import re
import base64
import mimetypes
import subprocess

EXPORT_BASE = Path('./exports')

# ─────────────────────────────────────────────────────────────────────────────
# Ajustes para decidir cuándo una tabla debe ir en una página horizontal.
# Se pueden afinar sin tocar el resto del código.
# ─────────────────────────────────────────────────────────────────────────────
PORTRAIT_WIDTH_PX      = 640    # ancho útil aprox. de una página A4 vertical (px CSS)
CHAR_PX                = 8.0    # ancho medio estimado de un carácter
CELL_PAD_PX            = 32     # padding horizontal total por columna (1rem + 1rem)
NATURAL_CAP_CHARS      = 32     # una celda "natural" no pasa de este nº de caracteres
NATURAL_OVERFLOW_RATIO = 1.35   # tolerancia antes de pasar a horizontal
LANDSCAPE_MIN_COLS     = 7      # 7 o más columnas → siempre horizontal

_TABLE_RE = re.compile(r'<table\b[^>]*>.*?</table>', re.DOTALL | re.IGNORECASE)
_ROW_RE   = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
_CELL_RE  = re.compile(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', re.DOTALL | re.IGNORECASE)
_TAG_RE   = re.compile(r'<[^>]+>')
# Fila separadora de tabla markdown con cualquier nº de columnas: | --- | :---: | ---: |
_SEP_RE   = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$')
# Encabezado (+ párrafo opcional) que está justo antes de una tabla:
# se mueve junto con la tabla a la página horizontal para no quedar huérfano.
_LEAD_RE  = re.compile(
    r'<h[1-6][^>]*>(?:(?!</h[1-6]>).)*</h[1-6]>\s*'
    r'(?:<p[^>]*>(?:(?!</p>).)*</p>\s*)?$',
    re.DOTALL | re.IGNORECASE,
)
_EMOJI_RE = re.compile('[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]')


class DocumentExporter:
    def __init__(self, project: dict, analysis_result: dict):
        self.project = project
        self.results = analysis_result.get('results', {})
        self.docs    = analysis_result.get('documentation', {})
        EXPORT_BASE.mkdir(parents=True, exist_ok=True)

    def to_markdown(self) -> str:
        return self.docs.get('full_markdown', '# Sin documentación generada')

    def _markdown_table_to_html(self, text: str) -> str:
        lines = text.split('\n')
        output = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if '|' in line and i + 1 < len(lines):
                sep_line = lines[i + 1]
                if _SEP_RE.match(sep_line):
                    headers = [cell.strip() for cell in re.split(r'\s*\|\s*', line.strip().strip('|'))]
                    rows = []
                    i += 2
                    while i < len(lines) and '|' in lines[i] and lines[i].strip():
                        row_cells = [cell.strip() for cell in re.split(r'\s*\|\s*', lines[i].strip().strip('|'))]
                        if len(row_cells) == len(headers):
                            rows.append(row_cells)
                        i += 1
                    head_html = ''.join(f'<th>{h}</th>' for h in headers)
                    body_html = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
                    output.append(f'<table class="report-table"><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>')
                    continue
            output.append(line)
            i += 1
        return '\n'.join(output)

    def _render_markdown_with_node(self, md: str) -> str:
        script_path = Path(__file__).resolve().parents[1] / 'markdown_to_html.js'
        if not script_path.exists():
            raise FileNotFoundError('Node markdown script not found')
        result = subprocess.run(
            ['node', str(script_path)],
            input=md,
            text=True,
            capture_output=True,
            cwd=script_path.parent,
            timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node markdown conversion failed: {result.stderr.strip()}")
        return result.stdout

    # ─────────────────────────────────────────────────────────────────────────
    # Tablas anchas → página horizontal (solo esa página)
    # ─────────────────────────────────────────────────────────────────────────
    def _is_wide_table(self, table_html: str) -> bool:
        """Estima si una tabla HTML cabe en una página A4 vertical."""
        grid = []
        for row in _ROW_RE.findall(table_html):
            cells = _CELL_RE.findall(row)
            texts = [re.sub(r'\s+', ' ', _html.unescape(_TAG_RE.sub('', c))).strip() for c in cells]
            if texts:
                grid.append(texts)
        if not grid:
            return False

        n_cols = max(len(r) for r in grid)
        if n_cols >= LANDSCAPE_MIN_COLS:
            return True

        min_total = 0.0   # ancho mínimo (palabra más larga de cada columna)
        nat_total = 0.0   # ancho "natural" (texto más largo, con tope)
        for c in range(n_cols):
            longest_token = 0
            longest_text = 0
            for r in grid:
                if c < len(r):
                    text = r[c]
                    longest_text = max(longest_text, len(text))
                    for tok in text.split():
                        longest_token = max(longest_token, len(tok))
            min_total += longest_token * CHAR_PX + CELL_PAD_PX
            nat_total += min(longest_text, NATURAL_CAP_CHARS) * CHAR_PX + CELL_PAD_PX

        return (min_total > PORTRAIT_WIDTH_PX
                or nat_total > PORTRAIT_WIDTH_PX * NATURAL_OVERFLOW_RATIO)

    def _wrap_wide_tables(self, html_body: str) -> str:
        """
        Envuelve cada tabla ancha en <div class="table-landscape">.
        La regla CSS `page: landscape` hace que solo esa página sea horizontal;
        el contenido anterior y posterior vuelve a orientación vertical.
        """
        out = []
        pos = 0
        for m in _TABLE_RE.finditer(html_body):
            table_html = m.group(0)
            if not self._is_wide_table(table_html):
                continue
            start, end = m.span()
            before = html_body[pos:start]
            lead = _LEAD_RE.search(before)
            if lead:
                out.append(before[:lead.start()])
                intro = before[lead.start():]
            else:
                out.append(before)
                intro = ''
            out.append(f'<div class="table-landscape">{intro}{table_html}</div>')
            pos = end
        out.append(html_body[pos:])
        return ''.join(out)

    def to_html(self) -> str:
        md = self.to_markdown()
        project_name = self.project.get('name', 'Proyecto')

        try:
            html_body = self._render_markdown_with_node(md)
        except Exception:
            try:
                from markdown import markdown as markdown_to_html
                html_body = markdown_to_html(md, extensions=['fenced_code', 'tables', 'attr_list', 'sane_lists', 'extra'])
            except Exception:
                html_body = md
                # Las tablas se convierten primero para que el reemplazo de '---' no rompa sus separadores
                html_body = self._markdown_table_to_html(html_body)
                html_body = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^### (.+)$',  r'<h3>\1</h3>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^## (.+)$',   r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^# (.+)$',    r'<h1>\1</h1>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
                html_body = re.sub(r'\*(.+?)\*',      r'<em>\1</em>',        html_body)
                html_body = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_body)
                html_body = re.sub(r'```[\w]*\n(.*?)```', r'<pre><code>\1</code></pre>', html_body, flags=re.DOTALL)
                html_body = re.sub(r'^---$', '<hr>', html_body, flags=re.MULTILINE)

        # Todas las tablas comparten el mismo diseño (el de «Stack Tecnológico»)
        html_body = re.sub(r'<table(?![^>]*class=)', '<table class="report-table"', html_body)

        # Inject section IDs onto h1/h2/h3 headings
        sec_counter = [0]
        toc_headings = []
        def inject_section_id(m):
            sec_counter[0] += 1
            tag = m.group(1)
            text = m.group(2)
            level = int(tag[1])
            plain_text = re.sub(r'<[^>]+>', '', text).strip()
            toc_headings.append((level, plain_text, sec_counter[0]))
            return f'<{tag} id="sec{sec_counter[0]}">{text}</{tag}>'
        html_body = re.sub(r'<(h[123])>(.*?)</\1>', inject_section_id, html_body, flags=re.DOTALL)

        def _build_toc_html(headings):
            if not headings:
                return '<p style="color:var(--muted)">No se detectaron secciones.</p>'
            html_parts = ['<ul class="toc-list">']
            top_counter = 0
            for level, text, sec_id in headings:
                if level == 1:
                    top_counter += 1
                    label = f'{top_counter}. {text}'
                else:
                    label = text
                css_class = f'toc-h{level}'
                html_parts.append(
                    f'<li class="{css_class}"><a href="#sec{sec_id}">{label}</a></li>'
                )
            html_parts.append('</ul>')
            return ''.join(html_parts)

        toc_html = _build_toc_html(toc_headings)

        # Tablas anchas → solo esa página en horizontal
        html_body = self._wrap_wide_tables(html_body)

        # Wrap diagram heading + image
        html_body = re.sub(
            r'(<h3>(2\.\d+\s+Diagrama[^<]*)</h3>)(\s*(?:<p>\s*)?(<img[^>]+>)(?:\s*</p>)?)',
            lambda m: (
                f'<div class="diagram-section">'
                f'<h3>{m.group(2)}</h3>'
                f'{m.group(4)}'
                f'</div>'
            ),
            html_body,
            flags=re.DOTALL
        )

        def image_replacer(match):
            attrs = match.group(1)
            src = match.group(2)
            if src.startswith('http://') or src.startswith('https://') or src.startswith('data:'):
                resolved_src = src
            else:
                try:
                    image_path = Path(src)
                    if not image_path.is_absolute():
                        image_path = Path.cwd() / image_path
                    if not image_path.exists():
                        image_path = EXPORT_BASE / image_path.name
                    if image_path.exists():
                        mime_type = mimetypes.guess_type(str(image_path))[0] or 'image/png'
                        encoded = base64.b64encode(image_path.read_bytes()).decode('ascii')
                        resolved_src = f'data:{mime_type};base64,{encoded}'
                    else:
                        resolved_src = src
                except Exception:
                    resolved_src = src
            return f'<img src="{resolved_src}" {attrs} style="max-width: 60%; max-height: 380px; width: auto; height: auto; display: block; margin: 1.5rem auto; border: 1px solid var(--border); border-radius: 8px;">'

        html_body = re.sub(r'<img\s+([^>]*?)src=["\']([^"\']+)["\']([^>]*)>', image_replacer, html_body)

        score = self.results.get('quality_score', 0)
        score_color = '#10b981' if score >= 70 else '#f59e0b' if score >= 40 else '#ef4444'
        score_label = 'Excelente' if score >= 80 else 'Aceptable' if score >= 60 else 'Requiere mejoras'
        primary_lang = self.results.get('primary_language', '—')
        generated_at = datetime.utcnow().strftime('%d/%m/%Y %H:%M')

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} — Documentación Técnica</title>
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet">
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0b1120; --surface: #151d30; --surface2: #1a2540;
    --border: #2a3a5c; --border-light: #334670;
    --accent: #38bdf8; --accent2: #818cf8; --accent3: #34d399; --accent4: #f472b6;
    --text: #c8d6e5; --text2: #8899b0; --muted: #5c6f8a; --white: #f0f4f8;
    --radius: 12px; --radius-sm: 8px; --radius-lg: 16px;
  }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 11.5pt; line-height: 1.7; text-align: justify;
  }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 3rem 2rem; }}

  /* ── PORTADA ──────────────────────────── */
  .doc-header {{
    background:
      radial-gradient(circle at 92% 0%, rgba(129,140,248,0.22) 0%, transparent 42%),
      radial-gradient(circle at 0% 100%, rgba(56,189,248,0.16) 0%, transparent 45%),
      linear-gradient(160deg, var(--surface) 0%, var(--surface2) 100%);
    border: 1px solid var(--border); border-radius: var(--radius-lg);
    padding: 4rem 2.5rem 2.5rem; margin-bottom: 3rem;
    position: relative; overflow: hidden;
    display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
  }}
  .doc-header::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 6px;
    background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent4), #f59e0b);
  }}
  .cover-eyebrow {{
    display: inline-block; padding: 0.4rem 1.2rem; border-radius: 100px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.22em; text-transform: uppercase; color: var(--accent);
    background: rgba(56,189,248,0.10); border: 1px solid rgba(56,189,248,0.35);
  }}
  .cover-title {{
    font-size: 2.9rem; font-weight: 800; color: var(--white);
    line-height: 1.1; letter-spacing: -0.02em; text-transform: uppercase;
    margin: 1.4rem 0 0.2rem; overflow-wrap: anywhere; text-align: center;
  }}
  .cover-rule {{
    width: 96px; height: 4px; border-radius: 4px; margin: 1.1rem auto 1.2rem;
    background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent4));
  }}
  .doc-header .subtitle {{
    color: var(--text2); font-size: 0.95rem; letter-spacing: 0.02em; text-align: center;
  }}
  .cover-meta {{
    display: flex; justify-content: center; gap: 1.2rem; flex-wrap: wrap; margin-top: 1.8rem;
  }}
  .cover-meta-item {{
    display: flex; flex-direction: column; align-items: center; gap: 0.15rem;
    padding: 0.55rem 1.3rem; border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  }}
  .cover-meta-item .cm-lbl {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.14em;
  }}
  .cover-meta-item .cm-val {{ font-size: 0.9rem; font-weight: 700; color: var(--white); }}
  .stats-row {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-top: 2rem; width: 100%;
  }}
  .stat {{
    background: rgba(255,255,255,0.03); border: 1px solid var(--border);
    border-top: 3px solid var(--accent);
    border-radius: var(--radius); padding: 1.1rem 0.8rem; text-align: center;
  }}
  .stat:nth-child(2) {{ border-top-color: var(--accent2); }}
  .stat:nth-child(3) {{ border-top-color: var(--accent3); }}
  .stat:nth-child(4) {{ border-top-color: var(--accent4); }}
  .stat .val {{ font-size: 1.9rem; font-weight: 800; color: var(--white); line-height: 1; }}
  .stat .lbl {{
    font-size: 0.68rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.12em; margin-top: 0.3rem;
    font-family: 'JetBrains Mono', monospace; font-weight: 600;
  }}
  .cover-brand {{
    margin-top: 2rem; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted);
  }}
  .cover-brand span {{ color: var(--accent); font-weight: 700; }}

  /* ── HEADINGS ──────────────────────────── */
  h1, h2, h3, h4 {{
    font-family: 'Inter', sans-serif; text-align: left;
    page-break-after: avoid; break-after: avoid-page;
  }}
  h1 {{
    font-size: 20pt; font-weight: 800; color: var(--white);
    margin: 2.5rem 0 1rem; padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--accent);
    position: relative;
  }}
  h1::after {{
    content: ''; position: absolute; bottom: -2px; left: 0;
    width: 80px; height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
  }}
  h2 {{
    font-size: 16pt; font-weight: 700; color: var(--white);
    margin: 2rem 0 0.75rem; padding-left: 0.85rem;
    border-left: 3px solid var(--accent2);
  }}
  h3 {{
    font-size: 13pt; font-weight: 700; color: var(--accent);
    margin: 1.5rem 0 0.5rem; padding-left: 0.6rem;
    border-left: 3px solid rgba(56,189,248,0.3);
  }}
  h4 {{
    font-size: 12pt; font-weight: 600; color: var(--text);
    margin: 1rem 0 0.4rem;
  }}
  p, li {{ margin: 0.6rem 0; font-size: 11.5pt; text-align: justify; }}

  /* ── CODE ──────────────────────────────── */
  code {{
    background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.2);
    padding: 0.15rem 0.5rem; border-radius: 5px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.92rem;
    font-weight: 600; color: #7dd3fc;
  }}
  pre {{
    background: linear-gradient(180deg, #0a1628 0%, #0d1b2a 100%);
    border: 1px solid var(--border); border-left: 4px solid var(--accent);
    border-radius: var(--radius); padding: 1.25rem 1.5rem;
    overflow-x: auto; margin: 1rem 0;
    page-break-inside: avoid; break-inside: avoid;
  }}
  pre code {{
    background: none; border: none; padding: 0;
    color: #bae6fd; font-size: 0.9rem; font-weight: 500;
  }}

  /* ── TABLES (diseño único = «Stack Tecnológico») ───────── */
  table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    margin: 1.2rem 0; font-size: 0.9rem;
    border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden;
    page-break-inside: avoid; break-inside: avoid;
  }}
  .report-table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    margin: 1.2rem 0; font-size: 0.92rem;
    border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden;
    page-break-inside: avoid; break-inside: avoid;
  }}
  .report-table thead {{ display: table-header-group; }}
  .report-table thead tr {{ background: linear-gradient(180deg, rgba(56,189,248,0.12) 0%, rgba(56,189,248,0.04) 100%); }}
  .report-table th, .report-table td {{
    padding: 0.85rem 1rem; border-bottom: 1px solid var(--border);
    overflow-wrap: anywhere;
  }}
  .report-table th {{
    color: var(--white); text-align: left; font-weight: 700;
    text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.06em;
    background: rgba(15,23,42,0.95);
  }}
  .report-table tr {{ page-break-inside: avoid; break-inside: avoid; }}
  .report-table tr:last-child td {{ border-bottom: none; }}
  .report-table tr:nth-child(even) td {{ background: rgba(255,255,255,0.02); }}
  .report-table tr:hover td {{ background: rgba(56,189,248,0.04); }}
  .report-table td {{ color: var(--text); }}
  .report-table td code {{ white-space: normal; overflow-wrap: anywhere; }}
  th {{
    background: var(--surface); color: var(--white);
    padding: 0.75rem 1rem; text-align: left; font-weight: 700;
    border-bottom: 1px solid var(--border);
    text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.06em;
  }}
  td {{
    padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); color: var(--text);
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:nth-child(even) td {{ background: rgba(255,255,255,0.015); }}

  /* ── TABLAS ANCHAS → PÁGINA HORIZONTAL ─────────────────── */
  .table-landscape {{ max-width: 100%; }}
  .table-landscape table, .table-landscape .report-table {{
    page-break-inside: auto; break-inside: auto;
  }}

  /* ── CODE FRAGMENT ─────────────────────── */
  .code-fragment {{
    margin: 1.5rem 0; padding: 1.25rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius);
    page-break-inside: avoid; break-inside: avoid;
  }}
  .code-fragment-header {{
    display: flex; align-items: center; gap: 10px; margin-bottom: 0.8rem;
  }}
  .code-fragment-header .frag-icon {{
    width: 30px; height: 30px; border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; flex-shrink: 0;
  }}
  .code-fragment-header .frag-title {{
    font-weight: 700; font-size: 0.95rem; color: var(--white);
  }}
  .code-fragment-header .frag-file {{
    font-size: 0.75rem; color: var(--muted); font-family: 'JetBrains Mono', monospace;
  }}
  .code-explanation {{
    margin-top: 0.8rem; padding: 0.8rem 1rem;
    background: rgba(52,211,153,0.06); border: 1px solid rgba(52,211,153,0.15);
    border-radius: var(--radius-sm);
    font-size: 0.88rem; color: var(--text); line-height: 1.65;
  }}
  .code-explanation strong {{ color: var(--accent); }}

  /* ── MISC ──────────────────────────────── */
  blockquote {{
    border-left: 3px solid var(--accent3); padding: 0.9rem 1.1rem;
    background: rgba(52,211,153,0.07); border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    margin: 1rem 0; color: #6ee7b7; font-size: 1rem;
    font-weight: 500; font-style: italic;
    page-break-inside: avoid; break-inside: avoid;
  }}
  ul {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
  li {{ margin: 0.3rem 0; }}
  hr {{ border: none; height: 1px; background: linear-gradient(90deg, transparent, var(--border), transparent); margin: 2.5rem 0; }}
  strong {{ color: var(--white); font-weight: 700; }}
  em {{ color: var(--accent2); font-style: italic; }}

  /* ── TOC ────────────────────────────────── */
  .toc {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 1.5rem; margin-bottom: 2rem;
  }}
  .toc h3 {{ color: var(--white); margin: 0 0 1rem; display: flex; align-items: center; gap: 0.5rem; }}
  .toc-list {{ list-style: none; padding-left: 0; }}
  .toc-list li {{ margin: 0.35rem 0; }}
  .toc-list a {{ color: var(--accent); text-decoration: none; transition: color 0.2s; }}
  .toc-list a:hover {{ text-decoration: underline; color: var(--white); }}
  .toc-list .toc-h1 {{ font-weight: 700; font-size: 1rem; margin-top: 0.9rem; }}
  .toc-list .toc-h1 a {{ color: var(--white); }}
  .toc-list .toc-h2 {{ padding-left: 1.25rem; font-size: 0.92rem; }}
  .toc-list .toc-h3 {{ padding-left: 2.5rem; font-size: 0.85rem; }}
  .toc-list .toc-h3 a {{ color: var(--accent2); }}

  /* ── FOOTER ────────────────────────────── */
  .doc-footer {{
    margin-top: 4rem; padding: 2rem 1.5rem 1.5rem;
    border-top: 2px solid var(--border); text-align: center;
    color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    background: linear-gradient(180deg, var(--surface) 0%, var(--surface2) 100%);
    border-radius: var(--radius);
  }}
  .doc-footer span {{ color: var(--accent); font-weight: 700; }}
  .doc-footer .footer-grid {{ display: flex; justify-content: center; gap: 2.5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  .doc-footer .footer-item {{ display: flex; flex-direction: column; align-items: center; gap: 0.2rem; }}
  .doc-footer .footer-item .fi-label {{ color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; }}
  .doc-footer .footer-item .fi-val {{ color: var(--text); font-size: 0.82rem; }}
  .doc-footer .footer-divider {{ border: none; border-top: 1px solid var(--border); margin: 0.75rem 0; }}
  .doc-footer .footer-brand {{ color: var(--muted); font-size: 0.72rem; }}
  .diagram-section {{ margin: 2rem 0; page-break-inside: avoid; break-inside: avoid; }}

  @media print {{
    @page {{
      margin: 2cm;
      @bottom-center {{ content: "Página " counter(page) " de " counter(pages); font-family: 'JetBrains Mono', monospace; font-size: 9pt; color: #64748b; }}
    }}
    /* Página horizontal: la usan solo las tablas anchas (.table-landscape) */
    @page landscape {{
      size: A4 landscape;
      margin: 1.5cm;
    }}
    /* Todo lo demás vuelve explícitamente a vertical (si no, "page:auto" hereda la horizontal) */
    .content > * {{ page: portrait; }}
    .content > .table-landscape {{ page: landscape; }}
    .doc-footer {{ page: portrait; }}
    .doc-header {{ page-break-after: always; break-after: always; min-height: 85vh; }}
    .toc {{ page-break-after: always; break-after: always; }}
    h1, h2, h3, h4, h5, h6 {{
      page-break-after: avoid !important; break-after: avoid-page !important;
      break-inside: avoid !important;
    }}
    .diagram-section, .report-table, pre, blockquote, .stat, table, .code-fragment {{
      page-break-inside: avoid !important; break-inside: avoid !important;
    }}
    .table-landscape table, .table-landscape .report-table {{
      page-break-inside: auto !important; break-inside: auto !important;
    }}
    body {{ background: white !important; color: #1e293b !important; }}
    .container {{ max-width: 100%; padding: 0; }}
  }}
  .diagram-section h3 {{ margin-bottom: 0.75rem !important; page-break-after: avoid !important; break-after: avoid-page !important; }}
  .diagram-section img {{ margin-top: 0 !important; }}
  .material-icons {{ font-size: 1.2em; vertical-align: middle; }}
  .material-symbols-outlined {{ font-size: 1.2em; vertical-align: middle; }}
</style>
</head>
<body>
<div class="container">
  <div class="doc-header">
    <span class="cover-eyebrow">Documentación Técnica Profesional</span>
    <div class="cover-title">{project_name}</div>
    <div class="cover-rule"></div>
    <div class="subtitle">Arquitectura · API · Código · Calidad</div>
    <div class="cover-meta">
      <div class="cover-meta-item"><span class="cm-lbl">Lenguaje principal</span><span class="cm-val">{primary_lang}</span></div>
      <div class="cover-meta-item"><span class="cm-lbl">Score de calidad</span><span class="cm-val" style="color:{score_color}">{score}/100 · {score_label}</span></div>
      <div class="cover-meta-item"><span class="cm-lbl">Generado</span><span class="cm-val">{generated_at} UTC</span></div>
    </div>
    <div class="stats-row">
      <div class="stat"><div class="val">{self.results.get('total_files', 0)}</div><div class="lbl">Archivos</div></div>
      <div class="stat"><div class="val">{len(self.results.get('functions', []))}</div><div class="lbl">Funciones</div></div>
      <div class="stat"><div class="val">{len(self.results.get('classes', []))}</div><div class="lbl">Clases</div></div>
      <div class="stat"><div class="val">{len(self.results.get('endpoints', []))}</div><div class="lbl">Endpoints</div></div>
    </div>
    <div class="cover-brand">Generado por <span>AutoDocs AI</span></div>
  </div>
  <div class="toc">
    <h3><span class="material-icons">list</span> Tabla de Contenidos</h3>
    {toc_html}
  </div>
  <div class="content">{html_body}</div>
  <div class="doc-footer">
    <div class="footer-grid">
      <div class="footer-item">
        <span class="fi-label">Proyecto</span>
        <span class="fi-val">{project_name}</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Archivos</span>
        <span class="fi-val">{self.results.get('total_files', 0)}</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Clases</span>
        <span class="fi-val">{len(self.results.get('classes', []))}</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Funciones</span>
        <span class="fi-val">{len(self.results.get('functions', []))}</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Endpoints</span>
        <span class="fi-val">{len(self.results.get('endpoints', []))}</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Score</span>
        <span class="fi-val" style="color:{score_color}">{score}/100</span>
      </div>
      <div class="footer-item">
        <span class="fi-label">Generado</span>
        <span class="fi-val">{generated_at} UTC</span>
      </div>
    </div>
    <hr class="footer-divider">
    <div class="footer-brand">Generado automáticamente por <span>AutoDocs AI</span> &middot; Documentación Técnica Profesional</div>
  </div>
</div>
</body>
</html>"""

    def _is_valid_pdf(self, path: Path) -> bool:
        try:
            with path.open('rb') as f:
                header = f.read(5)
                if not header.startswith(b'%PDF'):
                    return False
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 2048))
                tail = f.read()
                return b'%%EOF' in tail
        except Exception:
            return False

    def to_pdf(self) -> str:
        html_content = self.to_html()
        output_path = EXPORT_BASE / f"{self.project['_id']}_docs.pdf"
        html_path   = EXPORT_BASE / f"{self.project['_id']}_docs.html"

        html_path.write_text(html_content, encoding='utf-8')

        # 1st attempt: WeasyPrint
        try:
            from weasyprint import HTML
            HTML(string=html_content, base_url=str(EXPORT_BASE.resolve())).write_pdf(str(output_path))
            if output_path.exists() and output_path.stat().st_size > 1000 and self._is_valid_pdf(output_path):
                print(f"[PDF] WeasyPrint generado exitosamente: {output_path.stat().st_size} bytes")
                return str(output_path)
            else:
                print(f"[PDF] WeasyPrint generó archivo inválido o muy pequeño")
                output_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[PDF] Error en WeasyPrint: {str(e)}")
            output_path.unlink(missing_ok=True)

        # 2nd attempt: ReportLab
        try:
            pdf_path = self._pdf_with_reportlab(str(output_path))
            pdf_obj = Path(pdf_path)
            if pdf_path and pdf_obj.exists() and pdf_obj.stat().st_size > 1000 and self._is_valid_pdf(pdf_obj):
                print(f"[PDF] ReportLab generado exitosamente: {pdf_obj.stat().st_size} bytes")
                return pdf_path
            else:
                print(f"[PDF] ReportLab generó archivo inválido o muy pequeño")
                pdf_obj.unlink(missing_ok=True)
        except Exception as e:
            import traceback
            print(f"[PDF] Error en ReportLab: {str(e)}")
            print(traceback.format_exc())
            Path(output_path).unlink(missing_ok=True)

        print(f"[PDF] Ambos métodos fallaron, usando HTML como fallback")
        return str(html_path)

    def _pdf_with_reportlab(self, output_path: str) -> str:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            BaseDocTemplate, PageTemplate, Frame, NextPageTemplate,
            Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak, KeepTogether,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.pdfgen import canvas as _pdfcanvas

        project_name = self.project.get('name', 'Proyecto')
        score = self.results.get('quality_score', 0)
        md = self.to_markdown()

        # ── Geometría de páginas (vertical y horizontal) ──────────────────────
        PORTRAIT   = A4
        LANDSCAPE  = landscape(A4)
        P_MARGIN   = 2.5 * cm
        L_MARGIN   = 1.5 * cm
        portrait_w  = PORTRAIT[0]  - 2 * P_MARGIN
        landscape_w = LANDSCAPE[0] - 2 * L_MARGIN

        class _AutoDocsDocTemplate(BaseDocTemplate):
            def __init__(self, filename, **kw):
                BaseDocTemplate.__init__(self, filename, pagesize=PORTRAIT, **kw)
                portrait_frame = Frame(
                    P_MARGIN, P_MARGIN, portrait_w, PORTRAIT[1] - 2 * P_MARGIN,
                    id='frame_portrait', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
                landscape_frame = Frame(
                    L_MARGIN, 2.0 * cm, landscape_w, LANDSCAPE[1] - 2.0 * cm - 1.5 * cm,
                    id='frame_landscape', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
                self.addPageTemplates([
                    PageTemplate(id='portrait',  frames=[portrait_frame],  pagesize=PORTRAIT),
                    PageTemplate(id='landscape', frames=[landscape_frame], pagesize=LANDSCAPE),
                ])

            def afterFlowable(self, flowable):
                if isinstance(flowable, Paragraph):
                    style_name = getattr(flowable.style, 'name', '')
                    level_by_style = {'H1': 0, 'H2': 1, 'H3': 2}
                    if style_name in level_by_style:
                        text = flowable.getPlainText()
                        self.notify('TOCEntry', (level_by_style[style_name], text, self.page))

        class _NumberedCanvas(_pdfcanvas.Canvas):
            _SKIPPED_PAGES = 2

            def __init__(self, *args, **kwargs):
                _pdfcanvas.Canvas.__init__(self, *args, **kwargs)
                self._saved_page_states = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total_pages = len(self._saved_page_states)
                content_pages = max(total_pages - self._SKIPPED_PAGES, 0)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self._draw_page_number(content_pages)
                    _pdfcanvas.Canvas.showPage(self)
                _pdfcanvas.Canvas.save(self)

            def _draw_page_number(self, content_pages):
                page_num = self._pageNumber - self._SKIPPED_PAGES
                if page_num >= 1:
                    self.setFont('Helvetica', 8)
                    self.setFillColor(colors.HexColor('#64748b'))
                    # usa el ancho real de la página (vertical u horizontal)
                    self.drawCentredString(
                        self._pagesize[0] / 2, 1.2 * cm,
                        f"Página {page_num} de {content_pages}"
                    )

        doc = _AutoDocsDocTemplate(
            output_path,
            title=f"{project_name} — Documentación Técnica",
            author="AutoDocs AI",
        )

        base = getSampleStyleSheet()
        def S(name, parent='Normal', **kw):
            return ParagraphStyle(name, parent=base[parent], **kw)

        styles = {
            'title': S('T', 'Title', fontSize=24, textColor=colors.HexColor('#0f172a'), spaceAfter=8, alignment=TA_CENTER, keepWithNext=True),
            'sub': S('Su','Normal', fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=16, alignment=TA_CENTER, keepWithNext=True),
            'h1': S('H1','Heading1',fontSize=18, textColor=colors.HexColor('#0f172a'), spaceBefore=22, spaceAfter=8, keepWithNext=True),
            'h2': S('H2','Heading2',fontSize=14, textColor=colors.HexColor('#1e293b'), spaceBefore=18, spaceAfter=6, keepWithNext=True),
            'h3': S('H3','Heading3',fontSize=12, textColor=colors.HexColor('#334155'), spaceBefore=14, spaceAfter=4, keepWithNext=True),
            'h4': S('H4','Heading4',fontSize=10, textColor=colors.HexColor('#475569'), spaceBefore=10, spaceAfter=3, keepWithNext=True),
            'body': S('Bo','Normal', fontSize=12, fontName='Helvetica', textColor=colors.HexColor('#334155'), leading=17, alignment=TA_JUSTIFY, spaceAfter=5),
            'code': S('Co','Code', fontSize=10, textColor=colors.HexColor('#0369a1'),
                     backColor=colors.HexColor('#e0f2fe'), borderPad=5,
                     fontName='Courier-Bold', leading=14, spaceAfter=8),
            'quote': S('Qu','Normal', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#15803d'),
                     leftIndent=15, backColor=colors.HexColor('#dcfce7'), spaceAfter=8, alignment=TA_JUSTIFY),
            'location': S('Loc','Normal', fontSize=8, textColor=colors.HexColor('#64748b'),
                        leftIndent=10, spaceAfter=4, alignment=TA_JUSTIFY),
            'cell': S('Ce','Normal', fontSize=8.5, leading=11, fontName='Helvetica',
                      textColor=colors.HexColor('#334155'), alignment=TA_LEFT),
            'cell_head': S('CeH','Normal', fontSize=8.5, leading=11, fontName='Helvetica-Bold',
                           textColor=colors.white, alignment=TA_LEFT),
        }

        story = []

        # ── Portada ───────────────────────────────────────────────────────────
        score_hex = '#16a34a' if score >= 70 else '#ca8a04' if score >= 40 else '#dc2626'
        score_label = 'Excelente' if score >= 80 else 'Aceptable' if score >= 60 else 'Requiere mejoras'
        primary_lang = self.results.get('primary_language', '—')

        cover_eyebrow = S('CvE', 'Normal', fontSize=9, textColor=colors.HexColor('#93c5fd'),
                          alignment=TA_CENTER, fontName='Helvetica-Bold', leading=12)
        cover_title = S('CvT', 'Title', fontSize=30, leading=36, textColor=colors.white,
                        alignment=TA_CENTER, fontName='Helvetica-Bold')
        cover_sub = S('CvS', 'Normal', fontSize=11, leading=15, textColor=colors.HexColor('#cbd5e1'),
                      alignment=TA_CENTER)

        def _esc(t):
            return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        band = Table(
            [[Paragraph('DOCUMENTACIÓN TÉCNICA PROFESIONAL', cover_eyebrow)],
             [Paragraph(_esc(project_name.upper()), cover_title)],
             [Paragraph('Arquitectura · API · Código · Calidad', cover_sub)]],
            colWidths=[portrait_w],
        )
        band.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
            ('LINEABOVE', (0, 0), (-1, 0), 8, colors.HexColor('#3b82f6')),
            ('TOPPADDING', (0, 0), (-1, 0), 34),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 1), (-1, 1), 10),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 10),
            ('BOTTOMPADDING', (0, 2), (-1, 2), 34),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ]))

        kpi_vals = [str(self.results.get('total_files', 0)),
                    str(len(self.results.get('functions', []))),
                    str(len(self.results.get('classes', []))),
                    str(len(self.results.get('endpoints', [])))]
        kpi_lbls = ['ARCHIVOS', 'FUNCIONES', 'CLASES', 'ENDPOINTS']
        kpi_colors = ['#3b82f6', '#8b5cf6', '#10b981', '#ec4899']
        kpi_w = portrait_w / 4
        kpi = Table([kpi_vals, kpi_lbls], colWidths=[kpi_w] * 4)
        kpi_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f8fafc')),
            ('FONTSIZE', (0, 0), (-1, 0), 22),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1d4ed8')),
            ('FONTSIZE', (0, 1), (-1, 1), 7),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#64748b')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('INNERGRID', (0, 0), (-1, -1), 2, colors.white),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 1), (-1, 1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 12),
        ]
        for i, c in enumerate(kpi_colors):
            kpi_style.append(('LINEABOVE', (i, 0), (i, 0), 4, colors.HexColor(c)))
        kpi.setStyle(TableStyle(kpi_style))

        meta_style = S('CvM', 'Normal', fontSize=10, leading=15, textColor=colors.HexColor('#475569'),
                       alignment=TA_CENTER)
        story.append(Spacer(1, 2.5*cm))
        story.append(band)
        story.append(Spacer(1, 1.2*cm))
        story.append(kpi)
        story.append(Spacer(1, 1.2*cm))
        story.append(Paragraph(f"<b>Lenguaje principal:</b> {_esc(primary_lang)}", meta_style))
        story.append(Paragraph(
            f'<b>Score de calidad:</b> <font color="{score_hex}"><b>{score}/100 · {score_label}</b></font>',
            meta_style))
        story.append(Paragraph(
            f"<b>Generado:</b> {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC", meta_style))
        story.append(Spacer(1, 1.5*cm))
        story.append(HRFlowable(width="40%", thickness=2, color=colors.HexColor('#3b82f6'), hAlign='CENTER'))
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("Generado por AutoDocs AI", styles['sub']))
        story.append(PageBreak())

        # ── Índice ────────────────────────────────────────────────────────────
        toc = TableOfContents()
        toc.levelStyles = [
            S('TOC1', 'Normal', fontName='Helvetica-Bold', fontSize=12,
              leftIndent=0, firstLineIndent=0, spaceBefore=10, leading=16,
              textColor=colors.HexColor('#0f172a')),
            S('TOC2', 'Normal', fontName='Helvetica', fontSize=11,
              leftIndent=14, firstLineIndent=0, spaceBefore=4, leading=14,
              textColor=colors.HexColor('#334155')),
            S('TOC3', 'Normal', fontName='Helvetica-Oblique', fontSize=10,
              leftIndent=28, firstLineIndent=0, spaceBefore=2, leading=13,
              textColor=colors.HexColor('#64748b')),
        ]
        story.append(Paragraph('Tabla de Contenido', styles['h1']))
        story.append(Spacer(1, 0.5*cm))
        story.append(toc)
        story.append(PageBreak())

        # ── Contenido ─────────────────────────────────────────────────────────
        story.append(Paragraph(f"{project_name}", styles['title']))
        story.append(Paragraph("Documentación Técnica · AutoDocs AI · " +
                                datetime.utcnow().strftime('%d/%m/%Y'), styles['sub']))

        # Stats table
        row1 = [str(self.results.get('total_files', 0)),
                str(len(self.results.get('functions', []))),
                str(len(self.results.get('classes', []))),
                str(len(self.results.get('endpoints', [])))]
        row2 = ['Archivos', 'Funciones', 'Clases', 'Endpoints']
        t = Table([row1, row2], colWidths=[3.5*cm]*4)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTSIZE', (0,0), (-1,0), 18),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#f8fafc')),
            ('TEXTCOLOR', (0,1), (-1,1), colors.HexColor('#64748b')),
            ('FONTSIZE', (0,1), (-1,1), 7),
            ('FONTNAME', (0,1), (-1,1), 'Helvetica'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

        score_color = colors.HexColor('#16a34a') if score >= 70 else \
                      colors.HexColor('#ca8a04') if score >= 40 else colors.HexColor('#dc2626')
        score_style = S('Sc', 'Normal', fontSize=10, textColor=score_color,
                        alignment=TA_CENTER, spaceBefore=4, spaceAfter=10)
        story.append(Paragraph(f"Score de Calidad: {score}/100", score_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 0.4*cm))

        # Parse markdown
        in_code = False
        code_buf = []
        heading_anchor_counter = [0]

        def add_heading(raw_text, style, is_toc_level):
            text = raw_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
            if is_toc_level:
                heading_anchor_counter[0] += 1
                anchor = f'sec{heading_anchor_counter[0]}'
                text = f'<a name="{anchor}"/>{text}'
            try:
                para = Paragraph(text, style)
            except Exception:
                para = Paragraph(re.sub(r'<[^>]+>', '', text), style)
            para.keepWithNext = True
            story.append(para)

        def flush_code():
            if code_buf:
                txt = '\n'.join(code_buf).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                code_text = txt.replace('\n', '<br/>').replace(' ', '&nbsp;')
                code_para = Paragraph(code_text, styles['code'])
                story.append(code_para)
                story.append(Spacer(1, 0.3*cm))
                code_buf.clear()

        def inline_markup(text):
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
            text = re.sub(r'`([^`]+)`',
                          r'<font name="Courier-Bold" color="#0369a1" size="8">\1</font>', text)
            return text

        def safe_para(text, style):
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
            text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
            text = re.sub(r'`([^`]+)`',
                          r'<font name="Courier-Bold" color="#0369a1" size="10">\1</font>', text)
            if text.strip().startswith('**Ubicación:**'):
                text = text.replace('**Ubicación:**', '<b>Ubicación:</b>')
                style = styles['location']
            if text.strip().startswith('**Ejemplo de código:**'):
                text = text.replace('**Ejemplo de código:**', '<b>Ejemplo de código:</b>')
            if text.strip():
                try:
                    story.append(Paragraph(text, style))
                except Exception:
                    story.append(Paragraph(re.sub(r'<[^>]+>', '', text), style))

        def _fit_image_size(pil_size, max_w=10*cm, max_h=13*cm):
            w, h = pil_size
            if not w or not h:
                return max_w, max_h
            scale = min(max_w / w, max_h / h)
            return w * scale, h * scale

        def build_image_flowables(line):
            img_tags = re.findall(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>', line)
            if not img_tags:
                return []

            from reportlab.platypus import Image as RLImage
            try:
                from PIL import Image as PILImage
            except Exception:
                PILImage = None

            flowables = []
            for src in img_tags:
                if src.startswith('data:'):
                    try:
                        header, payload = src.split(',', 1)
                        data = base64.b64decode(payload)
                        if PILImage is not None:
                            with PILImage.open(io.BytesIO(data)) as im:
                                w, h = _fit_image_size(im.size)
                        else:
                            w, h = 10*cm, 13*cm
                        img = RLImage(io.BytesIO(data), width=w, height=h)
                        img.hAlign = 'CENTER'
                        flowables.append(img)
                        flowables.append(Spacer(1, 0.4*cm))
                    except Exception:
                        flowables.append(Paragraph('Imagen no disponible', styles['body']))
                else:
                    try:
                        image_path = Path(src)
                        if not image_path.is_absolute():
                            image_path = Path.cwd() / image_path
                        if image_path.exists():
                            if PILImage is not None:
                                with PILImage.open(str(image_path)) as im:
                                    w, h = _fit_image_size(im.size)
                            else:
                                w, h = 10*cm, 13*cm
                            img = RLImage(str(image_path), width=w, height=h)
                            img.hAlign = 'CENTER'
                            flowables.append(img)
                            flowables.append(Spacer(1, 0.4*cm))
                        else:
                            flowables.append(Paragraph('Imagen no encontrada: ' + src, styles['body']))
                    except Exception:
                        flowables.append(Paragraph('Imagen no disponible', styles['body']))
            return flowables

        def parse_table(lines, start_index):
            if start_index + 1 >= len(lines):
                return None
            header_line = lines[start_index].strip()
            sep_line = lines[start_index + 1].strip()
            if '|' not in header_line or not _SEP_RE.match(sep_line):
                return None

            headers = [cell.strip() for cell in re.split(r'\s*\|\s*', header_line.strip().strip('|'))]
            rows = []
            index = start_index + 2
            while index < len(lines):
                line = lines[index].strip()
                if not line or '|' not in line:
                    break
                row_cells = [cell.strip() for cell in re.split(r'\s*\|\s*', line.strip().strip('|'))]
                if len(row_cells) == len(headers):
                    rows.append(row_cells)
                else:
                    break
                index += 1

            if not rows:
                return None

            data = [headers] + rows
            return data, index - start_index

        # ── Tablas: texto con ajuste de línea, anchos proporcionales y orientación dinámica ──
        def _plain_cell(text):
            text = _EMOJI_RE.sub('', text)
            return re.sub(r'[*`]', '', text).strip()

        def _column_metrics(table_data):
            """Devuelve (anchos mínimos, anchos naturales) en puntos por columna."""
            n_cols = len(table_data[0])
            char_w, pad = 4.6, 12
            mins, nats = [], []
            for c in range(n_cols):
                longest_token = 1
                longest_text = 1
                for row in table_data:
                    txt = _plain_cell(row[c])
                    longest_text = max(longest_text, len(txt))
                    for tok in txt.split():
                        longest_token = max(longest_token, len(tok))
                mins.append(longest_token * char_w + pad)
                nats.append(min(longest_text, 30) * char_w + pad)
            return mins, nats

        def _is_wide(table_data):
            n_cols = len(table_data[0])
            if n_cols >= 7:
                return True
            mins, nats = _column_metrics(table_data)
            return sum(mins) > portrait_w or sum(nats) > portrait_w * 1.35

        def _col_widths(table_data, available):
            mins, nats = _column_metrics(table_data)
            total = sum(nats) or 1
            widths = [n * available / total for n in nats]
            widths = [max(w, min(m, available / len(widths))) for w, m in zip(widths, mins)]
            total = sum(widths) or 1
            return [w * available / total for w in widths]

        def build_report_table(table_data, available):
            data = []
            for r_idx, row in enumerate(table_data):
                st = styles['cell_head'] if r_idx == 0 else styles['cell']
                cells = []
                for cell in row:
                    txt = inline_markup(_EMOJI_RE.sub('', cell).strip())
                    try:
                        cells.append(Paragraph(txt, st))
                    except Exception:
                        cells.append(Paragraph(re.sub(r'<[^>]+>', '', txt), st))
                data.append(cells)
            tbl = Table(data, colWidths=_col_widths(table_data, available), repeatRows=1)
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8fafc'), colors.white]),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            return tbl

        # Estado de orientación: 'exit' guarda los marcadores [volver a vertical] de la última
        # tabla horizontal; si la siguiente tabla también es ancha se cancelan (misma página).
        state = {'exit': None}

        def _pop_lead_in():
            """Saca de la historia los encabezados/espacios previos a una tabla para llevarlos con ella."""
            pending = []
            while story and len(pending) < 12:
                last = story[-1]
                is_heading = isinstance(last, Paragraph) and getattr(last.style, 'name', '') in ('H1', 'H2', 'H3', 'H4')
                if isinstance(last, (Spacer, HRFlowable)) or is_heading:
                    pending.insert(0, story.pop())
                else:
                    break
            return pending

        def emit_wide_table(tbl, pending):
            ex = state['exit']
            if ex and len(story) >= 2 and story[-1] is ex[1] and story[-2] is ex[0]:
                story.pop(); story.pop()          # seguimos en horizontal, sin salto intermedio
            else:
                story.append(NextPageTemplate('landscape'))
                story.append(PageBreak())
            story.extend(pending)
            story.append(tbl)   # sin Spacer final: evita una página horizontal en blanco
            npt, pb = NextPageTemplate('portrait'), PageBreak()
            story.append(npt)
            story.append(pb)
            state['exit'] = (npt, pb)

        lines = md.split('\n')
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if line.strip().startswith('```'):
                if in_code:
                    flush_code()
                    in_code = False
                else:
                    in_code = True
                idx += 1
                continue
            if in_code:
                code_buf.append(line)
                idx += 1
                continue

            table_result = parse_table(lines, idx)
            if table_result:
                table_data, consumed = table_result
                if _is_wide(table_data):
                    pending = _pop_lead_in()
                    tbl = build_report_table(table_data, landscape_w)
                    emit_wide_table(tbl, pending)
                else:
                    tbl = build_report_table(table_data, portrait_w)
                    story.append(tbl)
                    story.append(Spacer(1, 0.3*cm))
                    state['exit'] = None
                idx += consumed
                continue

            diagram_heading = re.match(r'^###\s+(\d+\.\d+\s+Diagrama.*)$', line.strip())
            if diagram_heading:
                look = idx + 1
                while look < len(lines) and lines[look].strip() == '':
                    look += 1
                img_flowables = build_image_flowables(lines[look]) if look < len(lines) else []
                if img_flowables:
                    title_clean = (diagram_heading.group(1)
                                    .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
                    heading_anchor_counter[0] += 1
                    anchor = f'sec{heading_anchor_counter[0]}'
                    heading_para = Paragraph(f'<a name="{anchor}"/>{title_clean}', styles['h3'])
                    group = [heading_para, Spacer(1, 0.2*cm)] + img_flowables
                    story.append(KeepTogether(group))
                    idx = look + 1
                    state['exit'] = None
                    continue

            if line.strip() == '---':
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=colors.HexColor('#e2e8f0')))
                story.append(Spacer(1, 0.2*cm))
            elif line.startswith('#### '):
                add_heading(line[5:], styles['h4'], is_toc_level=False)
            elif line.startswith('### '):
                add_heading(line[4:], styles['h3'], is_toc_level=True)
            elif line.startswith('## '):
                add_heading(line[3:], styles['h2'], is_toc_level=True)
            elif line.startswith('# '):
                add_heading(line[2:], styles['h1'], is_toc_level=True)
            elif line.startswith('> '):
                safe_para(line[2:], styles['quote'])
            elif line.startswith(('- ', '* ')):
                safe_para('• ' + line[2:], styles['body'])
            elif line.strip() == '':
                story.append(Spacer(1, 0.15*cm))
            else:
                imgs = build_image_flowables(line)
                if imgs:
                    story.extend(imgs)
                else:
                    safe_para(line, styles['body'])
            # Cualquier contenido que no sea espacio/encabezado/separador "cierra" el modo horizontal
            if line.strip() and line.strip() != '---' and not line.startswith('#'):
                state['exit'] = None
            idx += 1

        if in_code:
            flush_code()

        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0')))
        story.append(Paragraph("Generado automáticamente por AutoDocs AI", styles['sub']))

        doc.multiBuild(story, canvasmaker=_NumberedCanvas)
        return output_path
