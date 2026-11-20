        page_word = self.t('page')
        of_word = self.t('of')
        css_project_name = safe_project_name.replace('\\', '\\\\').replace('"', '\\"')

        return f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{safe_project_name} — {self.t('tech_doc')}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  :root {{
    --ink: #1f2937;
    --ink-soft: #475569;
    --navy: #17365d;
    --blue: #2f5597;
    --blue-soft: #dbe7f5;
    --paper: #ffffff;
    --panel: #f4f7fb;
    --rule: #b8c5d6;
    --muted: #64748b;
    --score: {score_color};
  }}
  @page {{
    size: A4 portrait;
    margin: 2.35cm 2.15cm 2.2cm 2.15cm;
    @top-left {{
      content: "{self.t('page_header')}";
      color: #52657a;
      font-family: "Arial", sans-serif;
      font-size: 7.5pt;
      font-weight: 700;
      letter-spacing: .08em;
    }}
    @top-right {{
      content: "{css_project_name}";
      color: #52657a;
      font-family: "Arial", sans-serif;
      font-size: 7.5pt;
    }}
    @bottom-left {{
      content: "{self.t('technical_use')}";
      color: #718096;
      font-family: "Arial", sans-serif;
      font-size: 7.5pt;
    }}
    @bottom-right {{
      content: "{page_word} " counter(page) " {of_word} " counter(pages);
      color: #52657a;
      font-family: "Arial", sans-serif;
      font-size: 8pt;
    }}
  }}
  @page cover {{ margin: 0; @top-left {{ content: none; }} @top-right {{ content: none; }} @bottom-left {{ content: none; }} @bottom-right {{ content: none; }} }}
  @page contents {{ @top-left {{ content: "{self.t('index_header')}"; }} }}
  @page landscape {{ size: A4 landscape; margin: 1.7cm; }}

  html {{ font-size: 10.6pt; }}
  body {{
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: "Liberation Serif", "Times New Roman", serif;
    line-height: 1.55;
    text-rendering: optimizeLegibility;
  }}
  .cover {{
    page: cover;
    height: 297mm;
    padding: 31mm 25mm 24mm;
    display: flex;
    flex-direction: column;
    background: #fff;
    border-top: 11mm solid var(--navy);
    border-bottom: 4mm solid var(--navy);
  }}
  .cover-kicker {{
    color: var(--blue);
    font-family: "Arial", sans-serif;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: .18em;
    text-transform: uppercase;
    margin-top: 9mm;
  }}
  .cover h1 {{
    border: 0;
    color: var(--navy);
    font-family: "Arial", sans-serif;
    font-size: 29pt;
    font-weight: 700;
    line-height: 1.14;
    margin: 20mm 0 5mm;
    padding: 0;
    text-transform: none;
    overflow-wrap: anywhere;
  }}
  .cover-subtitle {{
    color: var(--ink-soft);
    font-family: "Arial", sans-serif;
    font-size: 14pt;
    line-height: 1.35;
    margin: 0;
    text-align: left;
  }}
  .cover-rule {{ width: 31mm; border-top: 1.2mm solid var(--blue); margin: 12mm 0 0; }}
  .cover-purpose {{
    max-width: 135mm;
    color: #465569;
    font-size: 11pt;
    line-height: 1.55;
    margin-top: 10mm;
    text-align: left;
  }}
  .cover-spacer {{ flex: 1; }}
  .cover-meta {{
    border-top: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    padding: 4mm 0;
    font-family: "Arial", sans-serif;
    font-size: 9pt;
  }}
  .cover-meta div {{ padding: 2.1mm 4mm 2.1mm 0; }}
  .cover-meta strong {{ display: block; color: var(--navy); font-size: 7.5pt; letter-spacing: .07em; text-transform: uppercase; }}
  .cover-score {{ color: var(--score); font-weight: 700; }}
  .cover-footer {{ color: var(--muted); font-family: "Arial", sans-serif; font-size: 8pt; margin-top: 7mm; }}

  .toc {{ page: contents; break-after: page; }}
  .toc-title {{
    color: var(--navy);
    font-family: "Arial", sans-serif;
    font-size: 21pt;
    border-bottom: 1.2mm solid var(--blue);
    padding-bottom: 3mm;
    margin: 0 0 10mm;
  }}
  .toc-intro {{ color: var(--ink-soft); font-size: 9.7pt; margin: 0 0 6mm; text-align: left; }}
  .toc-list {{ list-style: none; margin: 0; padding: 0; }}
  .toc-list li {{ margin: 0; padding: 1.25mm 0; break-inside: avoid; }}
  .toc-list a {{ color: var(--ink); display: block; text-decoration: none; }}
  .toc-list a::after {{ content: leader('.') target-counter(attr(href), page); color: var(--muted); }}
  .toc-list a span {{ background: #fff; padding-right: 1.5mm; }}
  .toc-h1 {{ border-top: 1px solid #dbe3ed; font-family: "Arial", sans-serif; font-size: 10pt; font-weight: 700; margin-top: 2.2mm !important; }}
  .toc-h2 {{ font-size: 9.2pt; padding-left: 6mm !important; }}
  .toc-h3 {{ color: var(--ink-soft); font-size: 8.5pt; padding-left: 12mm !important; }}
  .toc-empty {{ color: var(--muted); font-style: italic; }}

  .content {{ counter-reset: figure; }}
  h1, h2, h3, h4, h5, h6 {{
    color: var(--navy);
    font-family: "Arial", sans-serif;
    text-align: left;
    break-after: avoid-page;
    page-break-after: avoid;
    break-inside: avoid;
  }}
  h1 {{ font-size: 20pt; line-height: 1.2; border-bottom: 1.2mm solid var(--blue); margin: 12mm 0 6mm; padding: 0 0 3mm; }}
  h1:first-child {{ margin-top: 0; }}
  h2 {{ font-size: 15.5pt; line-height: 1.25; border-bottom: .35mm solid var(--rule); margin: 9mm 0 4mm; padding-bottom: 1.8mm; }}
  h3 {{ color: #244f7f; font-size: 12.4pt; line-height: 1.3; margin: 7mm 0 3mm; }}
  h4 {{ color: #35516f; font-size: 10.8pt; margin: 5mm 0 2mm; }}
  h5, h6 {{ color: #465f78; font-size: 10pt; margin: 4mm 0 1.5mm; }}
  p {{ margin: 0 0 3.4mm; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }}
  li {{ margin: 1.2mm 0; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }}
  ul, ol {{ margin: 2.5mm 0 4mm; padding-left: 7mm; }}
  strong {{ color: #172b43; font-weight: 700; }}
  em {{ color: #354d65; }}
  a {{ color: #1f5f99; }}
  hr {{ border: 0; border-top: .3mm solid #cbd5e1; margin: 8mm 0; }}
  blockquote {{
    margin: 4mm 0 5mm;
    padding: 3.5mm 5mm;
    background: var(--panel);
    border-left: 1.2mm solid var(--blue);
    color: #334155;
    font-style: normal;
    break-inside: avoid;
  }}
  blockquote p:last-child {{ margin-bottom: 0; }}
  code {{
    color: #17365d;
    background: #eef3f8;
    border: .2mm solid #d5e0eb;
    border-radius: 1mm;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8.7pt;
    padding: .2mm .8mm;
    overflow-wrap: anywhere;
  }}
  pre {{
    background: #f3f6f9;
    border: .25mm solid #cbd5e1;
    border-left: 1.1mm solid var(--blue);
    margin: 4mm 0 5mm;
    padding: 4mm;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    break-inside: auto;
  }}
  pre code {{ background: transparent; border: 0; color: #1e293b; padding: 0; }}
  table, .report-table {{
    width: 100%;
    border-collapse: collapse;
    border: .25mm solid #aebdce;
    font-family: "Arial", sans-serif;
    font-size: 8.25pt;
    line-height: 1.35;
    margin: 4mm 0 6mm;
  }}
  thead {{ display: table-header-group; }}
  th {{ background: var(--navy); color: #fff; font-weight: 700; padding: 2.4mm 2.7mm; text-align: left; vertical-align: top; }}
  td {{ border: .2mm solid #cbd5e1; color: #29384a; padding: 2.2mm 2.7mm; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
  tbody tr:nth-child(even) td {{ background: #f5f8fb; }}
  tr {{ break-inside: avoid; page-break-inside: avoid; }}
  td code {{ white-space: normal; }}
  img {{
    display: block;
    max-width: 92%;
    max-height: 190mm;
    width: auto;
    height: auto;
    margin: 5mm auto;
    border: .25mm solid #cbd5e1;
    padding: 2mm;
    break-inside: avoid;
  }}
  .table-landscape {{ page: landscape; }}
  .table-landscape table {{ break-inside: auto; }}
  .diagram-section {{ margin: 6mm 0; break-inside: avoid; page-break-inside: avoid; }}
  .diagram-section h3 {{ break-after: avoid; page-break-after: avoid; }}
  .diagram-section img {{ margin-top: 2mm; }}
  .code-fragment {{
    margin: 4mm 0 5mm;
    padding: 3.5mm 4mm;
    background: var(--panel);
    border: .25mm solid var(--rule);
    border-left: 1.1mm solid var(--blue);
    break-inside: avoid;
    page-break-inside: avoid;
  }}
  .code-fragment-header {{ margin-bottom: 2mm; }}
  .frag-title {{ font-family: "Arial", sans-serif; font-weight: 700; color: var(--navy); }}
  .frag-file {{ font-family: "Consolas", "Courier New", monospace; font-size: 8pt; color: var(--muted); }}
  .code-explanation {{ margin-top: 2.5mm; font-size: 9.5pt; color: #334155; line-height: 1.45; }}
  .code-explanation strong {{ color: var(--navy); }}
  .document-control {{
    margin-top: 12mm;
    border-top: .6mm solid var(--navy);
    padding-top: 4mm;
    color: var(--muted);
    font-family: "Arial", sans-serif;
    font-size: 8.3pt;
    break-inside: avoid;
  }}
  .document-control strong {{ color: var(--navy); }}
  @media screen {{
    body {{ background: #e8edf3; padding: 20px; }}
    .cover, .toc, .content {{ background: #fff; box-shadow: 0 2px 14px rgba(15, 23, 42, .14); margin: 0 auto 20px; max-width: 210mm; }}
    .toc, .content {{ padding: 22mm 20mm; }}
  }}
</style>
</head>
<body>
  <section class="cover">
    <div class="cover-kicker">{self.t('tech_doc_kicker')}</div>
    <h1>{safe_project_name}</h1>
    <p class="cover-subtitle">{self.t('tech_doc_sub2')}</p>
    <div class="cover-rule"></div>
    <p class="cover-purpose">{self.t('cover_purpose')}</p>
    <div class="cover-spacer"></div>
    <div class="cover-meta">
      <div><strong>{self.t('project')}</strong>{safe_project_name}</div>
      <div><strong>{self.t('issue_date')}</strong>{generated_at}</div>
      <div><strong>{self.t('primary_language')}</strong>{primary_lang}</div>
      <div><strong>{self.t('evaluation')}</strong><span class="cover-score">{self.t('score_of_quality')}: {score}/100 · {score_label}</span></div>
      <div><strong>{self.t('scope')}</strong>{total_files} {self.t('files').lower()} · {total_functions} {self.t('functions').lower()}</div>
      <div><strong>{self.t('elements')}</strong>{total_classes} {self.t('classes').lower()} · {total_endpoints} {self.t('endpoints').lower()}</div>
    </div>
    <div class="cover-footer">{self.t('technical_edition')}</div>
  </section>

  <section class="toc">
    <h1 class="toc-title">{self.t('toc_general')}</h1>
    <p class="toc-intro">{self.t('toc_intro')}</p>
    {toc_html}
  </section>

  <main class="content">
    {html_body}
    <div class="document-control">
      <strong>{self.t('doc_control')}</strong> {self.t('project')}: {safe_project_name}. {self.t('issue_date')}: {generated_at}. {self.t('scope')}: {total_files} {self.t('files').lower()}, {total_functions} {self.t('functions').lower()}, {total_classes} {self.t('classes').lower()} y {total_endpoints} {self.t('endpoints').lower()}. {self.t('score_of_quality')}: {score}/100.
    </div>
  </main>
</body>
</html>"""
