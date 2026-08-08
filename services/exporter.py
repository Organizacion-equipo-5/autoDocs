from pathlib import Path
from datetime import datetime
import io
import re
import base64
import mimetypes
import subprocess

EXPORT_BASE = Path('./exports')


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
                if re.match(r'^\s*\|?\s*(:?-+:?\s*\|)+\s*(:?-+:?\s*)?\|?\s*$', sep_line):
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
                html_body = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^### (.+)$',  r'<h3>\1</h3>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^## (.+)$',   r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'^# (.+)$',    r'<h1>\1</h1>', html_body, flags=re.MULTILINE)
                html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
                html_body = re.sub(r'\*(.+?)\*',      r'<em>\1</em>',        html_body)
                html_body = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_body)
                html_body = re.sub(r'```[\w]*\n(.*?)```', r'<pre><code>\1</code></pre>', html_body, flags=re.DOTALL)
                html_body = html_body.replace('---', '<hr>')
                html_body = self._markdown_table_to_html(html_body)

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

        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name} — Documentación Técnica</title>
<link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined" rel="stylesheet">
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;700;800&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --accent: #38bdf8; --accent2: #818cf8; --accent3: #34d399;
    --text: #cbd5e1; --muted: #64748b; --white: #f1f5f9;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: Arial, Helvetica, sans-serif; font-size: 12pt; line-height: 1.6; text-align: justify; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 3rem 2rem; }}
  .doc-header {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 2.5rem; margin-bottom: 3rem; position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }}
  .doc-header::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3)); }}
  .doc-header h1 {{ font-size: 2rem; font-weight: 800; color: var(--white); margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
  .doc-header .subtitle {{ color: var(--muted); font-size: 0.9rem; font-family: 'JetBrains Mono', monospace; }}
  .stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-top: 1.5rem; }}
  .stat {{ background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 1rem; text-align: center; }}
  .stat .val {{ font-size: 1.8rem; font-weight: 800; color: var(--white); }}
  .stat .lbl {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 0.2rem; font-family: 'JetBrains Mono', monospace; }}
  .quality-badge {{ display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.4rem 1rem; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); border-radius: 100px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: {score_color}; margin-top: 1rem; }}
  h1, h2, h3, h4 {{ font-family: Arial, Helvetica, sans-serif; text-align: left; }}
  h1 {{ font-size: 20pt; font-weight: 800; color: var(--white); margin: 2.5rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--accent); }}
  h2 {{ font-size: 16pt; font-weight: 700; color: var(--white); margin: 2rem 0 0.75rem; padding-left: 0.75rem; border-left: 3px solid var(--accent2); }}
  h3 {{ font-size: 13pt; font-weight: 700; color: var(--accent); margin: 1.5rem 0 0.5rem; }}
  h4 {{ font-size: 12pt; font-weight: 600; color: var(--text); margin: 1rem 0 0.4rem; }}
  p, li {{ margin: 0.75rem 0; font-size: 12pt; text-align: justify; }}
  code {{ background: rgba(56,189,248,0.14); border: 1px solid rgba(56,189,248,0.3); padding: 0.2rem 0.55rem; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 700; color: #7dd3fc; }}
  pre {{ background: #0d1b2a; border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; overflow-x: auto; margin: 1rem 0; }}
  pre code {{ background: none; border: none; padding: 0; color: #bae6fd; font-size: 0.95rem; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
  .report-table {{ width: 100%; border-collapse: collapse; margin: 1.2rem 0; font-size: 0.95rem; }}
  .report-table thead tr {{ background: rgba(56,189,248,0.08); }}
  .report-table th, .report-table td {{ padding: 0.85rem 1rem; border: 1px solid var(--border); }}
  .report-table th {{ color: var(--white); text-align: left; font-weight: 700; background: rgba(15,23,42,0.95); }}
  .report-table tr:nth-child(even) td {{ background: rgba(255,255,255,0.03); }}
  .report-table td {{ color: var(--text); }}
  th {{ background: var(--surface); color: var(--white); padding: 0.7rem 1rem; text-align: left; font-weight: 600; border: 1px solid var(--border); }}
  td {{ padding: 0.6rem 1rem; border: 1px solid var(--border); color: var(--text); }}
  tr:nth-child(even) td {{ background: rgba(255,255,255,0.02); }}
  blockquote {{ border-left: 3px solid var(--accent3); padding: 0.9rem 1.1rem; background: rgba(52,211,153,0.1); border-radius: 0 8px 8px 0; margin: 1rem 0; color: #6ee7b7; font-size: 1.05rem; font-weight: 600; font-style: italic; }}
  ul {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
  li {{ margin: 0.3rem 0; }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 2.5rem 0; }}
  strong {{ color: var(--white); font-weight: 700; }}
  em {{ color: var(--accent2); font-style: italic; }}
  .toc {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; }}
  .toc h3 {{ color: var(--white); margin: 0 0 1rem; display: flex; align-items: center; gap: 0.5rem; }}
  .toc-list {{ list-style: none; padding-left: 0; }}
  .toc-list li {{ margin: 0.35rem 0; }}
  .toc-list a {{ color: var(--accent); text-decoration: none; }}
  .toc-list a:hover {{ text-decoration: underline; }}
  .toc-list .toc-h1 {{ font-weight: 700; font-size: 1rem; margin-top: 0.9rem; }}
  .toc-list .toc-h1 a {{ color: var(--white); }}
  .toc-list .toc-h2 {{ padding-left: 1.25rem; font-size: 0.92rem; }}
  .toc-list .toc-h3 {{ padding-left: 2.5rem; font-size: 0.85rem; }}
  .toc-list .toc-h3 a {{ color: var(--accent2); }}
  .doc-footer {{ margin-top: 4rem; padding: 2rem 1.5rem 1.5rem; border-top: 2px solid var(--border); text-align: center; color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; background: var(--surface); border-radius: 12px; }}
  .doc-footer span {{ color: var(--accent); font-weight: 700; }}
  .doc-footer .footer-grid {{ display: flex; justify-content: center; gap: 2.5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  .doc-footer .footer-item {{ display: flex; flex-direction: column; align-items: center; gap: 0.2rem; }}
  .doc-footer .footer-item .fi-label {{ color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; }}
  .doc-footer .footer-item .fi-val {{ color: var(--text); font-size: 0.82rem; }}
  .doc-footer .footer-divider {{ border: none; border-top: 1px solid var(--border); margin: 0.75rem 0; }}
  .doc-footer .footer-brand {{ color: var(--muted); font-size: 0.72rem; }}
  .diagram-section {{ margin: 2rem 0; }}
  @media print {{
    @page {{ margin: 2cm; @bottom-center {{ content: "Página " counter(page) " de " counter(pages); font-family: 'JetBrains Mono', monospace; font-size: 9pt; color: #64748b; }} }}
    .doc-header {{ page-break-after: always; min-height: 85vh; }}
    .toc {{ page-break-after: always; }}
    h2 {{ page-break-before: auto; page-break-after: avoid; }}
    h3 {{ page-break-after: avoid; }}
    .diagram-section {{ page-break-inside: avoid; }}
    pre {{ page-break-inside: avoid; }}
    body {{ background: white !important; color: #1e293b !important; }}
    .container {{ max-width: 100%; padding: 0; }}
  }}
  .diagram-section h3 {{ margin-bottom: 0.75rem !important; }}
  .diagram-section img {{ margin-top: 0 !important; }}
  .material-icons {{ font-size: 1.2em; vertical-align: middle; }}
  .material-symbols-outlined {{ font-size: 1.2em; vertical-align: middle; }}
</style>
</head>
<body>
<div class="container">
  <div class="doc-header">
    <h1><span class="material-icons">description</span> {project_name}</h1>
    <div class="subtitle">Documentación Técnica Profesional · Generado {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC</div>
    <div class="quality-badge">Score de Calidad: {score}/100</div>
    <div class="stats-row">
      <div class="stat"><div class="val">{self.results.get('total_files', 0)}</div><div class="lbl">Archivos</div></div>
      <div class="stat"><div class="val">{len(self.results.get('functions', []))}</div><div class="lbl">Funciones</div></div>
      <div class="stat"><div class="val">{len(self.results.get('classes', []))}</div><div class="lbl">Clases</div></div>
      <div class="stat"><div class="val">{len(self.results.get('endpoints', []))}</div><div class="lbl">Endpoints</div></div>
    </div>
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
        <span class="fi-val">{datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC</span>
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
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable, PageBreak, KeepTogether,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.pdfgen import canvas as _pdfcanvas

        project_name = self.project.get('name', 'Proyecto')
        score = self.results.get('quality_score', 0)
        md = self.to_markdown()

        class _AutoDocsDocTemplate(SimpleDocTemplate):
            _toc_anchor_counter = 0

            def afterFlowable(self, flowable):
                if isinstance(flowable, Paragraph):
                    style_name = getattr(flowable.style, 'name', '')
                    level_by_style = {'H1': 0, 'H2': 1, 'H3': 2}
                    if style_name in level_by_style:
                        self._toc_anchor_counter += 1
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
                    self.drawCentredString(
                        A4[0] / 2, 1.2 * cm,
                        f"Página {page_num} de {content_pages}"
                    )

        doc = _AutoDocsDocTemplate(
            output_path, pagesize=A4,
            leftMargin=2.5*cm, rightMargin=2.5*cm,
            topMargin=2.5*cm, bottomMargin=2.5*cm,
            title=f"{project_name} — Documentación Técnica",
            author="AutoDocs AI",
        )

        base = getSampleStyleSheet()
        def S(name, parent='Normal', **kw):
            return ParagraphStyle(name, parent=base[parent], **kw)

        styles = {
            'title': S('T', 'Title', fontSize=24, textColor=colors.HexColor('#0f172a'), spaceAfter=8, alignment=TA_CENTER),
            'sub': S('Su','Normal', fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=16, alignment=TA_CENTER),
            'h1': S('H1','Heading1',fontSize=18, textColor=colors.HexColor('#0f172a'), spaceBefore=20, spaceAfter=8),
            'h2': S('H2','Heading2',fontSize=14, textColor=colors.HexColor('#1e293b'), spaceBefore=16, spaceAfter=6),
            'h3': S('H3','Heading3',fontSize=12, textColor=colors.HexColor('#334155'), spaceBefore=12, spaceAfter=4),
            'h4': S('H4','Heading4',fontSize=10, textColor=colors.HexColor('#475569'), spaceBefore=10, spaceAfter=3),
            'body': S('Bo','Normal', fontSize=12, fontName='Helvetica', textColor=colors.HexColor('#334155'), leading=17, alignment=TA_JUSTIFY, spaceAfter=5),
            'code': S('Co','Code', fontSize=10, textColor=colors.HexColor('#0369a1'),
                     backColor=colors.HexColor('#e0f2fe'), borderPad=5,
                     fontName='Courier-Bold', leading=14, spaceAfter=8),
            'quote': S('Qu','Normal', fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#15803d'),
                     leftIndent=15, backColor=colors.HexColor('#dcfce7'), spaceAfter=8, alignment=TA_JUSTIFY),
            'location': S('Loc','Normal', fontSize=8, textColor=colors.HexColor('#64748b'),
                        leftIndent=10, spaceAfter=4, alignment=TA_JUSTIFY),
        }

        story = []

        # Portada simplificada
        story.append(Spacer(1, 4*cm))
        story.append(Paragraph(project_name.upper(), styles['title']))
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph("Documentación Técnica", styles['sub']))
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph(f"Generado: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC", styles['sub']))
        story.append(Spacer(1, 2*cm))
        story.append(Paragraph("AutoDocs AI", styles['sub']))
        story.append(PageBreak())

        # Índice
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

        # Contenido
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
                story.append(Paragraph(text, style))
            except Exception:
                story.append(Paragraph(re.sub(r'<[^>]+>', '', text), style))

        def flush_code():
            if code_buf:
                txt = '\n'.join(code_buf).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                code_text = txt.replace('\n', '<br/>').replace(' ', '&nbsp;')
                code_para = Paragraph(code_text, styles['code'])
                story.append(code_para)
                story.append(Spacer(1, 0.3*cm))
                code_buf.clear()

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
            if '|' not in header_line or not re.match(r'^\s*\|?\s*(:?-+:?\s*\|)+\s*(:?-+:?\s*)?\|?\s*$', sep_line):
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
                tbl = Table(table_data, colWidths=[None] * len(table_data[0]))
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#334155')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 0.3*cm))
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
            idx += 1

        if in_code:
            flush_code()

        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0')))
        story.append(Paragraph("Generado automáticamente por AutoDocs AI", styles['sub']))

        doc.multiBuild(story, canvasmaker=_NumberedCanvas)
        return output_path