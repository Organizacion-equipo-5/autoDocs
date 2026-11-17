"""
services/ci_report.py

Genera los textos Markdown que usa la integración con GitHub:

- render_pr_comment(): comentario de PR con el cambio del score de calidad.
- render_project_report(): documento resumen (docs/AUTODOCS.md) para commits en main.

Solo usa la librería estándar (lo consume la GitHub Action sin instalar nada).
"""

COMMENT_MARKER = "<!-- autodocs-quality-report -->"
MAX_LIST = 8

# Métricas que se muestran en la tabla del PR, en este orden
PR_METRICS = (
    "functions", "classes", "endpoints", "documented_functions",
    "avg_complexity", "high_complexity_funcs",
    "dead_code", "duplicated_lines", "hot_files",
)


def _cell(text) -> str:
    """Escapa un valor para una celda de tabla Markdown."""
    return str(text if text is not None else "—").replace("|", "\\|").replace("\n", " ")


def _code(text) -> str:
    return f"`{str(text).replace('`', chr(39))}`"


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _signed(delta) -> str:
    if delta is None:
        return "—"
    return f"{delta:+g}"


def _icon(delta, lower_is_better=False) -> str:
    if not delta:
        return "⚪"
    good = delta < 0 if lower_is_better else delta > 0
    return "🟢" if good else "🔴"


def _short_sha(source) -> str:
    return (source or {}).get("sha", "")[:7]


def score_band(score) -> str:
    score = score or 0
    if score >= 80:
        return "Excelente"
    if score >= 60:
        return "Bueno"
    return "Necesita mejoras"


def _bullets(title, items, render, total):
    if not items:
        return []
    lines = [f"**{title}** ({total})"]
    lines += [f"- {render(i)}" for i in items[:MAX_LIST]]
    if total > MAX_LIST:
        lines.append(f"- … y {total - MAX_LIST} más")
    lines.append("")
    return lines


def render_pr_comment(diff: dict, head: dict, base: dict = None, gate: dict = None) -> str:
    """
    Comentario de PR con el cambio de calidad.

    Args:
        diff: resultado de analysis_history.diff_snapshots(base, head).
        head: snapshot del PR (para mostrar nivel y commit).
        base: snapshot de la rama base.
        gate: {"fail_under": int|None, "max_drop": int|None, "failed": [str]} para avisar
              del incumplimiento de los umbrales configurados.
    """
    score = diff["score"]
    delta = score.get("delta")
    lines = [COMMENT_MARKER, "## 📊 AutoDocs — Reporte de calidad", ""]

    if delta:
        verdict = "mejora" if delta > 0 else "baja"
        lines.append(
            f"El score de calidad {verdict} de **{_fmt(score['old'])}** a "
            f"**{_fmt(score['new'])}** ({_signed(delta)})."
        )
    else:
        lines.append(f"El score de calidad se mantiene en **{_fmt(score['new'])}**.")
    lines.append("")

    lines += ["| Métrica | Base | PR | Cambio |", "|---|---:|---:|---:|"]
    lines.append(
        f"| **Score de calidad** ({score_band(head.get('quality_score'))}) | "
        f"{_fmt(score['old'])} | {_fmt(score['new'])} | "
        f"{_icon(delta)} {_signed(delta)} |"
    )
    for key in PR_METRICS:
        m = diff["totals"].get(key)
        if not m:
            continue
        d = m.get("delta")
        lines.append(
            f"| {_cell(m['label'])} | {_fmt(m['old'])} | {_fmt(m['new'])} | "
            f"{_icon(d, m['lower_is_better'])} {_signed(d)} |"
        )
    lines.append("")

    ep, fn, cl = diff["endpoints"], diff["functions"], diff["classes"]
    lines += _bullets("Endpoints nuevos", ep["added"],
                      lambda e: f"{_code(e['method'] + ' ' + e['path'])} — {_code(e['file'])}",
                      ep["counts"]["added"])
    lines += _bullets("Endpoints eliminados", ep["removed"],
                      lambda e: _code(e["method"] + " " + e["path"]), ep["counts"]["removed"])
    lines += _bullets("Clases nuevas", cl["added"],
                      lambda c: f"{_code(c['name'])} — {_code(c['file'])}", cl["counts"]["added"])
    lines += _bullets("Clases eliminadas", cl["removed"],
                      lambda c: f"{_code(c['name'])} — {_code(c['file'])}", cl["counts"]["removed"])

    complex_new = [f for f in fn["added"] if f.get("complexity", 1) > 10]
    lines += _bullets("⚠️ Funciones nuevas con complejidad alta (>10)", complex_new,
                      lambda f: f"{_code(f['name'])} — {_code(f['file'])} (complejidad {f['complexity']})",
                      len(complex_new))
    lines += _bullets("Funciones nuevas", fn["added"],
                      lambda f: f"{_code(f['name'])} — {_code(f['file'])}", fn["counts"]["added"])
    lines += _bullets("Funciones eliminadas", fn["removed"],
                      lambda f: f"{_code(f['name'])} — {_code(f['file'])}", fn["counts"]["removed"])

    worse = sorted((c for c in fn["changed"] if c["complexity_delta"] > 0),
                   key=lambda c: -c["complexity_delta"])
    lines += _bullets("Funciones que ahora son más complejas", worse,
                      lambda c: f"{_code(c['name'])} — {_code(c['file'])} (+{c['complexity_delta']})",
                      len(worse))

    heat = [h for h in diff["hotspots"] if h["old"] is None or h["new"] > h["old"]]
    lines += _bullets("Archivos más calientes", heat,
                      lambda h: f"{_code(h['file'])}: {_fmt(h['old'])} → {_fmt(h['new'])}",
                      len(heat))

    if not diff["summary"]["has_changes"]:
        lines += ["_Este PR no cambia funciones, clases, endpoints ni el score._", ""]

    if gate and gate.get("failed"):
        lines += ["### ❌ Umbrales de calidad no cumplidos", ""]
        lines += [f"- {msg}" for msg in gate["failed"]]
        lines.append("")

    sha = _short_sha(head.get("source"))
    base_sha = _short_sha((base or {}).get("source"))
    footer = "Generado por AutoDocs AI"
    if sha:
        footer += f" · commit {sha}" + (f" vs {base_sha}" if base_sha else "")
    lines.append(f"<sub>{footer}</sub>")
    return "\n".join(lines).rstrip() + "\n"


def render_project_report(snapshot: dict, health: dict = None, project_name: str = "") -> str:
    """Documento Markdown con el resumen del proyecto (se versiona en docs/AUTODOCS.md)."""
    t = snapshot.get("totals", {})
    src = snapshot.get("source", {})
    title = project_name or src.get("repo") or "Proyecto"
    score = snapshot.get("quality_score", 0)

    lines = [f"# Documentación automática — {title}", ""]
    meta = [f"Lenguaje principal: **{snapshot.get('primary_language', 'unknown')}**",
            f"Score de calidad: **{score}/100** ({score_band(score)})"]
    if src.get("sha"):
        meta.append(f"Commit: `{src['sha'][:7]}`")
    lines += ["  \n".join(meta), "", "## Resumen", "",
              "| Métrica | Valor |", "|---|---:|"]
    for key in ("files", "functions", "classes", "endpoints", "documented_functions",
                "avg_complexity", "high_complexity_funcs", "dead_code",
                "duplicated_lines", "hot_files"):
        if key in t:
            label = key.replace("_", " ").capitalize()
            lines.append(f"| {label} | {_fmt(t[key])} |")
    lines.append("")

    endpoints = snapshot.get("endpoints", [])
    if endpoints:
        lines += ["## Endpoints", "", "| Método | Ruta | Archivo |", "|---|---|---|"]
        for e in sorted(endpoints, key=lambda e: (e["path"], e["method"]))[:200]:
            lines.append(f"| {_cell(e['method'])} | {_cell(_code(e['path']))} | {_cell(_code(e['file']))} |")
        lines.append("")

    classes = snapshot.get("classes", [])
    if classes:
        lines += ["## Clases", "", "| Clase | Archivo | Métodos |", "|---|---|---:|"]
        for c in sorted(classes, key=lambda c: (c["file"], c["name"]))[:200]:
            lines.append(f"| {_cell(_code(c['name']))} | {_cell(_code(c['file']))} | {len(c.get('methods', []))} |")
        lines.append("")

    hot = (health or {}).get("heatmap", {}).get("files", [])[:10]
    if hot:
        lines += ["## Archivos con mayor complejidad", "",
                  "| Archivo | Riesgo | Nivel | Líneas | Funciones |", "|---|---:|---|---:|---:|"]
        for h in hot:
            lines.append(f"| {_cell(_code(h['file']))} | {h['score']} | {h['level']} | "
                         f"{h['loc']} | {h['functions']} |")
        lines.append("")

    dead = (health or {}).get("dead_code", {}).get("items", [])[:15]
    if dead:
        lines += ["## Posible código muerto", ""]
        lines += [f"- {_code(d['name'])} — {_code(d['file'] + ':' + str(d['line']))}" for d in dead]
        lines.append("")

    dups = (health or {}).get("duplicates", {}).get("items", [])[:10]
    if dups:
        lines += ["## Bloques duplicados", ""]
        for g in dups:
            where = ", ".join(_code(f"{o['file']}:{o['start_line']}") for o in g["occurrences"][:4])
            lines.append(f"- {g['lines']} líneas repetidas en {where}")
        lines.append("")

    lines.append("_Generado automáticamente por AutoDocs AI._")
    return "\n".join(lines) + "\n"
