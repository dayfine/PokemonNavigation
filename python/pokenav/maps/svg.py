"""Draws a grid, its named tiles and route walks over the map image, as SVG.

Look at it before trusting a grid: a row or column off shows as walls on
open ground. Then look at a run's routes on it: a leg "to wall" that the
walk logged as stopping on "limit" ended somewhere the grid has no wall.
"""
import base64
from html import escape

#  Fill per grid character: walls, tall grass, ledges, signs, doors.
STYLE = {
    '#': ('#d00', 0.30),
    '"': ('#0a0', 0.30),
    'v': ('#a0f', 0.45),
    'S': ('#f80', 0.65),
    'D': ('#06f', 0.65),
    'N': ('#f0f', 0.55),
}


def _tile_box(source, x, y):
    ox, oy = source.origin
    return ox + source.tile_px * x, oy + source.tile_px * y


def _centre(source, places):
    """The middle of the tiles of `places` on this map, or None."""
    mine = [(x, y) for (name, x, y) in places if name == source.name]
    if not mine:
        return None
    x = sum(p[0] for p in mine) / len(mine)
    y = sum(p[1] for p in mine) / len(mine)
    px, py = _tile_box(source, x, y)
    return px + source.tile_px / 2, py + source.tile_px / 2


def _text(x, y, label, colour):
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{colour}" font-size="8" font-family="Helvetica" '
            f'font-weight="bold" stroke="white" stroke-width="2.5" paint-order="stroke">{escape(label)}</text>')


def render(source, image_png=None, walks=(), title=''):
    w = source.image_size[0] or source.origin[0] * 2 + source.tile_px * source.width
    h = source.image_size[1] or source.tile_px * len(source.rows)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -26 {w} {h + 26}" width="{w * 2}" height="{(h + 26) * 2}" style="background:#fff">']
    if image_png:
        data = base64.b64encode(image_png).decode()
        parts.append(f'<image href="data:image/png;base64,{data}" x="0" y="0" width="{w}" height="{h}" preserveAspectRatio="none"/>')
    t = source.tile_px
    for y, row in enumerate(source.rows):
        for x, ch in enumerate(row):
            if ch not in STYLE:
                continue
            colour, opacity = STYLE[ch]
            px, py = _tile_box(source, x, y)
            parts.append(f'<rect x="{px}" y="{py}" width="{t}" height="{t}" fill="{colour}" fill-opacity="{opacity}"/>')
    #  Every fifth line, numbered, to read coordinates off the picture.
    for x in range(0, source.width + 1, 5):
        px, _ = _tile_box(source, x, 0)
        parts.append(f'<line x1="{px}" y1="0" x2="{px}" y2="{h}" stroke="#000" stroke-opacity="0.25" stroke-width="0.5"/>')
        parts.append(_text(px + 1, -3, str(x), '#000'))
    for y in range(0, len(source.rows) + 1, 5):
        _, py = _tile_box(source, 0, y)
        parts.append(f'<line x1="0" y1="{py}" x2="{w}" y2="{py}" stroke="#000" stroke-opacity="0.25" stroke-width="0.5"/>')
        parts.append(_text(1, py + 8, str(y), '#000'))
    for name, (x, y) in source.tiles.items():
        px, py = _tile_box(source, x, y)
        parts.append(f'<rect x="{px}" y="{py}" width="{t}" height="{t}" fill="none" stroke="#000" stroke-width="1.5"/>')
        parts.append(_text(px, py - 2, name, '#036'))
    palette = ['#e00', '#06c', '#c60', '#090', '#90c']
    for i, walk in enumerate(walks):
        colour = palette[i % len(palette)]
        points = [p for p in [_centre(source, walk.start)] + [_centre(source, leg.ends) for leg in walk.legs]]
        drawn = [p for p in points if p]
        if len(drawn) >= 2:
            path = ' '.join(f'{x:.1f},{y:.1f}' for x, y in drawn)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2.5" stroke-linejoin="round" opacity="0.85"/>')
        for n, (leg, end) in enumerate(zip(walk.legs, points[1:]), 1):
            if not end:
                continue
            bad = leg.to_wall and leg.stop and leg.stop != 'blocked'
            parts.append(f'<circle cx="{end[0]:.1f}" cy="{end[1]:.1f}" r="{4 if bad else 2.5}" '
                         f'fill="{"#ff0" if bad else "#fff"}" stroke="{colour}" stroke-width="1.5"/>')
            note = f'{n} {leg.direction} {leg.tiles}{"" if leg.to_wall else " open"}{f" ({leg.stop})" if leg.stop else ""}'
            parts.append(_text(end[0] + 5, end[1] + 3, note, colour))
        if drawn:
            parts.append(_text(drawn[0][0] + 5, drawn[0][1] - 5, walk.label, colour))
    if title:
        parts.append(f'<text x="{w / 2}" y="-16" text-anchor="middle" font-size="9" font-family="Helvetica" font-weight="bold">{escape(title)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts)
