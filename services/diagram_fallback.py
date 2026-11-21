"""
services/diagram_fallback.py

Dibuja localmente (con Pillow) los diagramas PlantUML que genera AutoDocs cuando no se
puede obtener la imagen ni con PlantUML local ni con los servidores remotos. Así el
documento siempre lleva la imagen incrustada y no solo un enlace.

Soporta el subconjunto de PlantUML que usa el proyecto:
  class "Nombre" as alias <<Estereotipo>> { +miembro() ... }
  [Componente] as alias        database/actor/usecase/entity "Etiqueta" as alias
  package/rectangle/node/folder/cloud "Nombre" { ... }
  a --> b : etiqueta           title Texto

No pretende reemplazar a PlantUML: es un respaldo sencillo y legible.
"""
import io
import math
import re
from collections import defaultdict
from typing import Optional

try:  # Pillow es opcional: sin él el respaldo simplemente no se usa.
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageFont = None

SCALE = 2                 # se dibuja al doble y se reduce: bordes y texto más nítidos
MAX_NODES = 60            # protección ante diagramas enormes
MAX_ROWS_PER_COLUMN = 5   # una capa con más elementos se reparte en varias columnas
MAX_PIXELS = 4200         # lado máximo del PNG final

_CONTAINERS = {'package', 'rectangle', 'node', 'folder', 'frame', 'cloud'}
_NODE_KINDS = {'class', 'interface', 'entity', 'database', 'actor', 'usecase', 'component', 'abstract'}

_NODE_RE = re.compile(
    r'^(?P<kind>abstract\s+class|class|interface|entity|database|actor|usecase|component)\s+'
    r'(?:"(?P<q>[^"]*)"|(?P<w>[\w.]+))'
    r'(?:\s+as\s+(?P<alias>[\w.]+))?'
    r'(?:\s*<<(?P<stereo>[^>]*)>>)?'
    r'\s*(?P<open>\{)?\s*$'
)
_COMPONENT_RE = re.compile(r'^\[(?P<label>[^\]]+)\](?:\s+as\s+(?P<alias>[\w.]+))?\s*$')
_CONTAINER_RE = re.compile(
    r'^(?P<kind>package|rectangle|node|folder|frame|cloud)\s+'
    r'(?:"(?P<q>[^"]*)"|(?P<w>[\w.]+))(?:\s+as\s+(?P<alias>[\w.]+))?\s*\{\s*$'
)
_EDGE_RE = re.compile(
    r'^(?P<a>[\w.]+|\[[^\]]+\])\s*(?P<arrow>[-.o*<|]*[-.]+[>|*o]*)\s*'
    r'(?P<b>[\w.]+|\[[^\]]+\])\s*(?::\s*(?P<label>.*)|\s{2,}(?P<label2>\S.*))?$'
)

_PALETTE = {
    'class': ('#EAF2FB', '#2F5D8A'),
    'entity': ('#FFF4DC', '#B7791F'),
    'component': ('#F1F5F9', '#475569'),
    'database': ('#E6F6EC', '#2F855A'),
    'actor': ('#FFFFFF', '#1F2937'),
    'usecase': ('#EEF2FF', '#4F46E5'),
    'container': ('#F8FAFC', '#94A3B8'),
}


def _font(size: int, bold: bool = False):
    names = (
        ['DejaVuSans-Bold.ttf', 'arialbd.ttf', 'LiberationSans-Bold.ttf'] if bold
        else ['DejaVuSans.ttf', 'arial.ttf', 'LiberationSans-Regular.ttf']
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:  # Pillow antiguo sin tamaño variable
        return ImageFont.load_default()


# ─── Lectura del PlantUML ────────────────────────────────────────────────────

class _Node:
    def __init__(self, alias, label, kind, stereo='', members=None, container=None):
        self.alias, self.label, self.kind = alias, label, kind
        self.stereo, self.members, self.container = stereo, members or [], container
        self.x = self.y = self.w = self.h = 0


def _norm_kind(kind: str) -> str:
    kind = kind.replace('abstract class', 'class').replace('abstract', 'class')
    return 'class' if kind == 'interface' else kind


def parse(code: str):
    """Devuelve (titulo, nodos{alias: _Node}, aristas[(a, b, etiqueta)], contenedores[(nombre, [alias])])."""
    title = ''
    nodes, edges, containers = {}, [], []
    stack = []            # contenedores abiertos (índices en `containers`)
    current_class = None  # nodo cuyo cuerpo { ... } estamos leyendo
    anon = 0

    def add_node(alias, label, kind, stereo=''):
        nonlocal anon
        if not alias:
            anon += 1
            alias = f'_n{anon}'
        node = nodes.get(alias) or _Node(alias, label, kind, stereo)
        node.label, node.kind, node.stereo = label or node.label, kind, stereo or node.stereo
        if stack:
            node.container = stack[-1]
            containers[stack[-1]][1].append(alias)
        nodes[alias] = node
        return node

    for raw in (code or '').splitlines():
        line = raw.strip()
        if not line or line.startswith(("'", '@start', '@end', 'skinparam', 'hide ', 'left to right',
                                        'top to bottom', '!', 'scale ', 'legend', 'note ')):
            continue
        if current_class is not None:
            if line == '}':
                current_class = None
            else:
                current_class.members.append(re.sub(r'^[+\-#~]\s*', '', line).strip())
            continue
        if line.lower().startswith('title '):
            title = line[6:].strip()
            continue
        if line == '}':
            if stack:
                stack.pop()
            continue

        m = _CONTAINER_RE.match(line)
        if m:
            containers.append((m.group('q') or m.group('w'), []))
            stack.append(len(containers) - 1)
            continue
        m = _NODE_RE.match(line)
        if m:
            label = m.group('q') if m.group('q') is not None else m.group('w')
            alias = m.group('alias') or (m.group('w') if m.group('w') else None)
            node = add_node(alias, label, _norm_kind(m.group('kind')), m.group('stereo') or '')
            if m.group('open'):
                current_class = node
            continue
        m = _COMPONENT_RE.match(line)
        if m:
            add_node(m.group('alias'), m.group('label'), 'component')
            continue
        m = _EDGE_RE.match(line)
        if m and '-' in m.group('arrow') or (m and '.' in m.group('arrow')):
            def clean(ref):
                return ref[1:-1] if ref.startswith('[') else ref
            label = (m.group('label') or m.group('label2') or '').strip()
            edges.append((clean(m.group('a')), clean(m.group('b')), label))

    # Aristas hacia elementos no declarados: se crean como elementos simples
    for a, b, _ in edges:
        for ref in (a, b):
            if ref not in nodes:
                nodes[ref] = _Node(ref, ref, 'component')
    return title, nodes, edges, containers


# ─── Posicionamiento por capas ───────────────────────────────────────────────

def _layers(nodes, edges):
    """Capa = camino más largo desde los orígenes (se ignoran las aristas que cierran ciclos)."""
    adj = defaultdict(list)
    for a, b, _ in edges:
        if a != b:
            adj[a].append(b)
    state, back = {}, set()

    def dfs(u):
        state[u] = 1
        for v in adj[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2

    for alias in nodes:
        if alias not in state:
            dfs(alias)

    layer = {alias: 0 for alias in nodes}
    for _ in range(len(nodes)):
        changed = False
        for a, b, _ in edges:
            if a != b and (a, b) not in back and layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break
    return layer


def _measure(node, draw, fonts):
    pad = 10 * SCALE
    f_title, f_text, f_small = fonts
    lines = [node.label] + ([f'«{node.stereo}»'] if node.stereo else [])
    widths = [draw.textlength(t, font=f_title) for t in lines]
    if node.kind in ('class', 'entity'):
        widths += [draw.textlength(t, font=f_small) for t in node.members]
        node.w = int(max(widths) + 2 * pad)
        head = (len(lines) * 20 + 10) * SCALE
        node.h = int(head + (len(node.members) * 16 + 10) * SCALE if node.members else head)
        node._head = head
    elif node.kind == 'actor':
        node.w, node.h = int(max(max(widths) + 2 * pad, 60 * SCALE)), 86 * SCALE
    elif node.kind == 'usecase':
        node.w, node.h = int(max(widths) + 4 * pad), 46 * SCALE
    elif node.kind == 'database':
        node.w, node.h = int(max(widths) + 2 * pad), 58 * SCALE
    else:
        node.w, node.h = int(max(widths) + 2 * pad), (len(lines) * 20 + 22) * SCALE


def _place(nodes, edges, draw, fonts):
    for n in nodes.values():
        _measure(n, draw, fonts)
    layer = _layers(nodes, edges)
    by_layer = defaultdict(list)
    for alias in nodes:                       # conserva el orden de aparición
        by_layer[layer[alias]].append(nodes[alias])

    gap_x, gap_y, margin = 70 * SCALE, 34 * SCALE, 30 * SCALE
    x = margin
    for li in sorted(by_layer):
        items = by_layer[li]
        total_h = sum(n.h + gap_y for n in items)
        if len(items) > MAX_ROWS_PER_COLUMN or total_h > 900 * SCALE:
            # Reparte en columnas de altura parecida para que el diagrama no quede largo y angosto
            avg_w = sum(n.w for n in items) / len(items) + gap_x
            target_h = max(max(n.h for n in items) + gap_y, math.sqrt(total_h * avg_w / 1.5))
            columns, col, col_h = [], [], 0
            for n in items:
                if col and col_h + n.h > target_h:
                    columns.append(col)
                    col, col_h = [], 0
                col.append(n)
                col_h += n.h + gap_y
            columns.append(col)
        else:
            columns = [items]
        for col in columns:
            col_w = max(n.w for n in col)
            y = margin
            for n in col:
                n.x, n.y = x + (col_w - n.w) // 2, y
                y += n.h + gap_y
            x += col_w + gap_x
    return layer


def _clip(node, tx, ty):
    """Punto del borde del nodo en la dirección del punto (tx, ty)."""
    cx, cy = node.x + node.w / 2, node.y + node.h / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (node.w / 2) / abs(dx) if dx else float('inf')
    sy = (node.h / 2) / abs(dy) if dy else float('inf')
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


# ─── Dibujo ──────────────────────────────────────────────────────────────────

def _arrow(draw, p1, p2, color, width):
    draw.line([p1, p2], fill=color, width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    size = 11 * SCALE
    left = (p2[0] - size * math.cos(ang - 0.45), p2[1] - size * math.sin(ang - 0.45))
    right = (p2[0] - size * math.cos(ang + 0.45), p2[1] - size * math.sin(ang + 0.45))
    draw.polygon([p2, left, right], fill=color)


def _draw_node(draw, n, fonts):
    f_title, f_text, f_small = fonts
    fill, line = _PALETTE.get(n.kind if n.kind in _PALETTE else 'component')
    x0, y0, x1, y1 = n.x, n.y, n.x + n.w, n.y + n.h
    lw = max(SCALE, 2)
    cx = (x0 + x1) / 2
    if n.kind in ('class', 'entity'):
        draw.rectangle([x0, y0, x1, y1], fill='#FFFFFF', outline=line, width=lw)
        draw.rectangle([x0, y0, x1, y0 + n._head], fill=fill, outline=line, width=lw)
        ty = y0 + 6 * SCALE
        if n.stereo:
            draw.text((cx, ty), f'«{n.stereo}»', font=f_small, fill='#64748B', anchor='ma')
            ty += 16 * SCALE
        draw.text((cx, ty), n.label, font=f_title, fill='#0F172A', anchor='ma')
        my = y0 + n._head + 6 * SCALE
        for member in n.members:
            draw.text((x0 + 10 * SCALE, my), member, font=f_small, fill='#334155')
            my += 16 * SCALE
    elif n.kind == 'actor':
        r = 9 * SCALE
        top = y0 + 2 * SCALE
        draw.ellipse([cx - r, top, cx + r, top + 2 * r], outline=line, width=lw)
        draw.line([cx, top + 2 * r, cx, top + 2 * r + 20 * SCALE], fill=line, width=lw)
        draw.line([cx - 14 * SCALE, top + 2 * r + 8 * SCALE, cx + 14 * SCALE, top + 2 * r + 8 * SCALE], fill=line, width=lw)
        draw.line([cx, top + 2 * r + 20 * SCALE, cx - 12 * SCALE, top + 2 * r + 36 * SCALE], fill=line, width=lw)
        draw.line([cx, top + 2 * r + 20 * SCALE, cx + 12 * SCALE, top + 2 * r + 36 * SCALE], fill=line, width=lw)
        draw.text((cx, y1 - 14 * SCALE), n.label, font=f_text, fill='#0F172A', anchor='ma')
    elif n.kind == 'usecase':
        draw.ellipse([x0, y0, x1, y1], fill=fill, outline=line, width=lw)
        draw.text((cx, (y0 + y1) / 2), n.label, font=f_text, fill='#0F172A', anchor='mm')
    elif n.kind == 'database':
        ry = 9 * SCALE
        draw.rectangle([x0, y0 + ry, x1, y1 - ry], fill=fill)
        draw.ellipse([x0, y1 - 2 * ry, x1, y1], fill=fill, outline=line, width=lw)
        draw.rectangle([x0 + lw, y0 + ry, x1 - lw, y1 - ry], fill=fill)
        draw.line([x0, y0 + ry, x0, y1 - ry], fill=line, width=lw)
        draw.line([x1, y0 + ry, x1, y1 - ry], fill=line, width=lw)
        draw.ellipse([x0, y0, x1, y0 + 2 * ry], fill=fill, outline=line, width=lw)
        draw.text((cx, (y0 + y1) / 2 + ry / 2), n.label, font=f_text, fill='#0F172A', anchor='mm')
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=8 * SCALE, fill=fill, outline=line, width=lw)
        draw.text((cx, (y0 + y1) / 2), n.label, font=f_title, fill='#0F172A', anchor='mm')


def render_png(code: str) -> Optional[bytes]:
    """PNG del diagrama o None si no se puede dibujar (sin Pillow, vacío o demasiado grande)."""
    if Image is None:
        return None
    try:
        title, nodes, edges, containers = parse(code)
        if not nodes or len(nodes) > MAX_NODES:
            return None

        fonts = (_font(13 * SCALE, bold=True), _font(12 * SCALE), _font(11 * SCALE))
        probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))
        _place(nodes, edges, probe, fonts)

        top_pad = (34 * SCALE) if title else 0
        pad = 30 * SCALE
        width = int(max(n.x + n.w for n in nodes.values()) + pad)
        height = int(max(n.y + n.h for n in nodes.values()) + pad + top_pad)
        img = Image.new('RGB', (width, height), '#FFFFFF')
        draw = ImageDraw.Draw(img)

        if top_pad:
            draw.text((width / 2, 10 * SCALE), title, font=fonts[0], fill='#0F172A', anchor='ma')
            for n in nodes.values():
                n.y += top_pad

        # Contenedores (package/rectangle) detrás de sus elementos
        for name, members in containers:
            boxes = [nodes[a] for a in members if a in nodes]
            if not boxes:
                continue
            x0 = min(n.x for n in boxes) - 14 * SCALE
            y0 = min(n.y for n in boxes) - 30 * SCALE
            x1 = max(n.x + n.w for n in boxes) + 14 * SCALE
            y1 = max(n.y + n.h for n in boxes) + 14 * SCALE
            fill, line = _PALETTE['container']
            draw.rounded_rectangle([x0, y0, x1, y1], radius=10 * SCALE, fill=fill, outline=line, width=SCALE)
            draw.text((x0 + 10 * SCALE, y0 + 7 * SCALE), name, font=fonts[0], fill='#475569')

        # Aristas (debajo de los elementos, para que no tapen el texto)
        for a, b, label in edges:
            na, nb = nodes[a], nodes[b]
            if na is nb:
                continue
            ca = (na.x + na.w / 2, na.y + na.h / 2)
            cb = (nb.x + nb.w / 2, nb.y + nb.h / 2)
            p1, p2 = _clip(na, *cb), _clip(nb, *ca)
            _arrow(draw, p1, p2, '#64748B', max(SCALE, 2))
            if label:
                mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                tw = draw.textlength(label, font=fonts[2])
                draw.rectangle([mx - tw / 2 - 3 * SCALE, my - 8 * SCALE, mx + tw / 2 + 3 * SCALE, my + 8 * SCALE], fill='#FFFFFF')
                draw.text((mx, my), label, font=fonts[2], fill='#475569', anchor='mm')

        for n in nodes.values():
            _draw_node(draw, n, fonts)

        # Se conserva el doble de resolución para que se vea nítido en el PDF; solo se
        # reduce si el diagrama es enorme.
        biggest = max(img.width, img.height)
        if biggest > MAX_PIXELS:
            ratio = MAX_PIXELS / biggest
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format='PNG', optimize=True)
        return out.getvalue()
    except Exception:
        return None
