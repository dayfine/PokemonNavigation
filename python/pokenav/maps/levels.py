#!/usr/bin/env python3
"""Level-aware map parser for Bulbapedia's DP maps (16 px tiles).

Pixels are walkable (paving, road, grass, curb), stairs, or blocked (rock
rims, buildings, trees, water). Walkable pixels are grouped into regions
(levels) by flood fill, so a rim stripe of any width separates them; regions
touch only through stairs. Each 16 px tile then takes the region holding
most of its walkable pixels, and a route may only step between tiles of the
same region, or across a stair tile into a region the stairs touch.

usage: levels.py MAP.bmp OUT_PREFIX [--profile town|sandtown|oreburgh|cave] [--min N] [--height H] [--objects on] [--edits FILE] [--offset x,y] [--stairs x,y]... [--from x,y]... [--to x,y]   (pixel coords)
writes OUT_PREFIX_regions.bmp, OUT_PREFIX_grid.txt, OUT_PREFIX_route.txt
"""
import struct, sys
from collections import deque, Counter

def load_bmp(path):
    b = open(path, 'rb').read()
    off = struct.unpack_from('<I', b, 10)[0]
    w, h = struct.unpack_from('<ii', b, 18)
    bpp = struct.unpack_from('<H', b, 28)[0] // 8
    rs = ((w * bpp) + 3) & ~3
    H = abs(h)
    px = [None] * (w * H)
    for y in range(H):
        r = (H - 1 - y) if h > 0 else y
        base = off + r * rs
        for x in range(w):
            i = base + x * bpp
            px[y * w + x] = (b[i + 2], b[i + 1], b[i])
    return w, H, px

def save_bmp(path, w, h, rgb):
    rs = ((w * 3) + 3) & ~3
    data = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b = rgb[y * w + x]
            row += bytes((b, g, r))
        row += b'\0' * (rs - w * 3)
        data += row
    hdr = b'BM' + struct.pack('<IHHI', 54 + len(data), 0, 0, 54)
    dib = struct.pack('<IiiHHIIiiII', 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    open(path, 'wb').write(hdr + dib + data)

WALK, STAIR, BLOCK = 0, 1, 2

PROFILE = 'town'
YSIZE = 0         # --height H: stretch a squashed image to H pixels tall
OBJECTS = False   # --objects on: rocks, people and crates on the floor block their tile
EDITS = []        # --edits FILE: tiles opened or blocked from what the console showed
MIN_TILE = 128    # walkable pixels a tile needs (of 256); caves use more, for small rocks

def classify(c, stair_colours):
    r, g, b = c
    if c in stair_colours:
        return STAIR
    if PROFILE == 'cave':
        # Oreburgh Mine floor browns; rocks, boulders, coal and walls differ.
        if c in ((120, 96, 72), (128, 104, 80), (104, 80, 56), (96, 80, 48), (136, 120, 80), (112, 88, 64)):
            return WALK
        return BLOCK
    if PROFILE == 'oreburgh':
        # Sand paths, and grey-brown dirt; the pink rock is redder (r - b > 35).
        if r >= 220 and g >= 180 and b >= 130 and r - b <= 100:
            return WALK
        if 80 <= r <= 140 and 12 <= r - b <= 30 and g >= b - 4:
            return WALK
        if abs(r - g) <= 14 and abs(g - b) <= 14 and 95 <= r <= 175:   # fences' shadows, gravel
            return WALK
        # Conveyor belts pass overhead: their blues and dark greys are ground
        # we walk under. The red pillars stay blocked.
        if (b >= r + 10 and g >= r) or c in ((77, 92, 92), (60, 82, 82), (46, 62, 62)):
            return WALK
        return BLOCK
    if PROFILE == 'sandtown':
        # Towns on dirt and sand (Sandgem): road (248, 224, 152), beach
        # (248, 248, 224). Roofs' pure white (248, 248, 248) stays blocked.
        if r >= 220 and g >= 180 and 120 <= b <= 230 and r - b <= 110:
            return WALK
    if abs(r - g) <= 14 and abs(g - b) <= 14 and abs(r - b) <= 14 and 95 <= r <= 215:
        return WALK
    if g >= 220 and r <= 130:
        return WALK
    if g >= 150 and b <= 80 and g > r:     # lighter grass
        return WALK
    if c in ((216, 200, 136), (192, 176, 120), (176, 160, 96), (136, 120, 80), (88, 80, 72)):
        return WALK                         # curbs and their outline

    return BLOCK

def main():
    args = sys.argv[1:]
    path, prefix = args[0], args[1]
    stair_pts = []; starts = []; goal = None; ox = oy = 0
    global PROFILE, MIN_TILE, OBJECTS, EDITS, YSIZE
    i = 2
    while i < len(args):
        k, v = args[i], args[i + 1]; i += 2
        if k == '--profile':
            PROFILE = v; continue
        if k == '--min':
            MIN_TILE = int(v); continue
        if k == '--height':
            YSIZE = int(v); continue
        if k == '--objects':
            OBJECTS = v == 'on'; continue
        if k == '--edits':
            EDITS = open(v).read().splitlines(); continue
        xy = tuple(int(t) for t in v.split(','))
        if k == '--stairs': stair_pts.append(xy)
        elif k == '--from': starts.append(xy)
        elif k == '--to': goal = xy
        elif k == '--offset': ox, oy = xy
    w, h, px = load_bmp(path)
    if YSIZE and YSIZE != h:
        # Some archive images are squashed vertically (Oreburgh Mine B2F is
        # 512x395 for a 512x512 map: its rocks are 12.5 px apart down, 16
        # across). Stretch back with nearest pixels.
        px = [px[(y * h // YSIZE) * w + x] for y in range(YSIZE) for x in range(w)]
        h = YSIZE
    # Stair colours: those common in the given stair tiles and rare elsewhere.
    sc = Counter()
    for (x, y) in stair_pts:
        for yy in range(y - 6, y + 6):
            for xx in range(x - 6, x + 6):
                sc[px[yy * w + xx]] += 1
    every = Counter(px)
    stair_colours = {c for c, n in sc.items() if n >= 4 and every[c] < 40 * len(stair_pts) * 12}
    kind = [classify(c, stair_colours) for c in px]
    # Flood fill walkable pixels into regions (4-connected).
    region = [-1] * (w * h)
    sizes = []
    for start in range(w * h):
        if kind[start] != WALK or region[start] >= 0:
            continue
        rid = len(sizes); region[start] = rid; q = deque([start]); n = 0
        while q:
            p = q.popleft(); n += 1
            x, y = p % w, p // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    np_ = ny * w + nx
                    if kind[np_] == WALK and region[np_] < 0:
                        region[np_] = rid; q.append(np_)
        sizes.append(n)
    # Stairs: each connected stair blob joins the regions it touches.
    links = set(); stair_region = [-1] * (w * h); blobs = []
    for start in range(w * h):
        if kind[start] != STAIR or stair_region[start] >= 0:
            continue
        bid = len(blobs); stair_region[start] = bid; q = deque([start]); touch = set()
        while q:
            p = q.popleft(); x, y = p % w, p // w
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h:
                    np_ = ny * w + nx
                    if kind[np_] == STAIR and stair_region[np_] < 0:
                        stair_region[np_] = bid; q.append(np_)
                    elif kind[np_] == WALK and sizes[region[np_]] >= 256:
                        touch.add(region[np_])
        blobs.append(touch)
    big = [i for i, s in enumerate(sizes) if s >= 2048]
    # Objects standing on the floor (rocks, boulders, people, crates): blobs
    # of non-walkable pixels that don't reach the image edge. A sprite may be
    # drawn smaller than a tile or off the tile grid; it blocks the tile under
    # its feet (bottom centre), and the tiles it covers for big ones.
    objects = []
    if OBJECTS:
        seen = [False] * (w * h)
        for st in range(w * h):
            if kind[st] == WALK or seen[st]:
                continue
            q = deque([st]); seen[st] = True; pts = []; edge = False
            while q:
                p = q.popleft(); pts.append(p); x, y = p % w, p // w
                if x in (0, w - 1) or y in (0, h - 1): edge = True
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        n = ny * w + nx
                        if kind[n] != WALK and not seen[n]: seen[n] = True; q.append(n)
            if not edge and 30 <= len(pts) <= 4000:
                xs = [p % w for p in pts]; ys = [p // w for p in pts]
                objects.append((min(xs), min(ys), max(xs), max(ys)))
    # Tiles.
    # A last row cut short by the image (at least half a tile) still counts.
    cols, rows = (w - ox) // 16, (h - oy + 8) // 16
    tile = [[None] * cols for _ in range(rows)]   # ('R', region) | ('S', set) | None
    for ty in range(rows):
        for tx in range(cols):
            cnt = Counter(); stairs = Counter()
            ys = range(oy + ty * 16, min(h, oy + ty * 16 + 16))
            for y in ys:
                for x in range(ox + tx * 16, ox + tx * 16 + 16):
                    p = y * w + x
                    if kind[p] == WALK and sizes[region[p]] >= 2048: cnt[region[p]] += 1
                    elif kind[p] == STAIR: stairs[stair_region[p]] += 1
            if stairs and sum(stairs.values()) >= 96:
                tile[ty][tx] = ('S', set().union(*(blobs[bid] for bid in stairs)))
            elif cnt:
                rid, n = cnt.most_common(1)[0]
                if n >= MIN_TILE * len(ys) // 16: tile[ty][tx] = ("R", rid)
    # Hand edits from the console: "open ROW COL0 COL1 [REGION_FROM_COL]" / "block ROW COL0 COL1".
    for line in EDITS:
        f = line.split()
        if not f or f[0].startswith('//'): continue
        r, c0, c1 = int(f[1]), int(f[2]), int(f[3])
        for c in range(c0, c1 + 1):
            if f[0] == 'block': tile[r][c] = None
            elif f[0] == 'open':
                near = next((tile[rr][cc] for rr, cc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1), (r - 2, c), (r + 2, c))
                             if 0 <= rr < rows and 0 <= cc < cols and tile[rr][cc] and tile[rr][cc][0] == 'R'), None)
                tile[r][c] = near or ('R', -1)
    for (x0, y0, x1, y1) in objects:
        feet = ((x0 + x1) // 2 - ox) // 16, (y1 - 2 - oy) // 16
        tiles = {feet}
        if x1 - x0 >= 24:   # boulders: every tile column they span, on the feet row
            tiles |= {((x - ox) // 16, feet[1]) for x in range(x0 + 4, x1 - 3, 8)}
        for tx, ty in tiles:
            if 0 <= tx < cols and 0 <= ty < rows: tile[ty][tx] = None
    def can(a, b):
        ta, tb = tile[a[1]][a[0]], tile[b[1]][b[0]]
        if ta is None or tb is None: return False
        if ta[0] == 'R' and tb[0] == 'R': return ta[1] == tb[1]
        if ta[0] == 'S' and tb[0] == 'S': return True
        s, r = (ta, tb) if ta[0] == 'S' else (tb, ta)
        return r[1] in s[1]
    # Grid text: region letters, '=' stairs, '#' blocked.
    letters = {}
    alpha = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    lines = []
    for ty in range(rows):
        s = ''
        for tx in range(cols):
            t = tile[ty][tx]
            if t is None: s += '#'
            elif t[0] == 'S': s += '='
            else:
                if t[1] not in letters: letters[t[1]] = alpha[len(letters) % len(alpha)]
                s += letters[t[1]]
        lines.append(s)
    open(prefix + '_grid.txt', 'w').write(f'{ox} {oy}\n' + '\n'.join(lines) + '\n')
    for i, l in enumerate(lines): print('%2d %s' % (i, l))
    # Region image.
    pal = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
           (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
           (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (0, 0, 128)]
    out = []
    for p in range(w * h):
        c = px[p]
        if kind[p] == WALK and sizes[region[p]] >= 2048:
            q = pal[big.index(region[p]) % len(pal)]
            out.append(tuple((c[k] + 2 * q[k]) // 3 for k in range(3)))
        elif kind[p] == STAIR:
            out.append((255, 255, 255))
        else:
            out.append(tuple(v // 3 for v in c))
    save_bmp(prefix + '_regions.bmp', w, h, out)
    # Route.
    if goal and starts:
        to_tile = lambda xy: ((xy[0] - ox) // 16, (xy[1] - oy) // 16)
        g = to_tile(goal)
        for s in starts:
            a = to_tile(s); prev = {a: None}; q = deque([a])
            while q:
                c = q.popleft()
                if c == g: break
                for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (c[0] + d[0], c[1] + d[1])
                    if 0 <= n[0] < cols and 0 <= n[1] < rows and n not in prev and can(c, n):
                        prev[n] = c; q.append(n)
            if g not in prev:
                seen = Counter(lines[y][x] for (x, y) in prev)
                print('no route from', s, 'start tile', a, tile[a[1]][a[0]], 'reached', dict(seen))
                for (x, y) in prev:
                    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        n = (x + d[0], y + d[1])
                        if 0 <= n[0] < cols and 0 <= n[1] < rows and n not in prev and tile[n[1]][n[0]] is not None and tile[n[1]][n[0]][0] == 'S':
                            print('  blocked stair edge', (x, y), tile[y][x], '->', n, tile[n[1]][n[0]])
                continue
            path = [g]
            while prev[path[-1]]: path.append(prev[path[-1]])
            path.reverse()
            corners = [path[0]] + [path[i] for i in range(1, len(path) - 1)
                       if (path[i][0] - path[i-1][0], path[i][1] - path[i-1][1]) != (path[i+1][0] - path[i][0], path[i+1][1] - path[i][1])] + [path[-1]]
            print('route from', s, len(path) - 1, 'steps:', corners)
            with open(prefix + '_route.txt', 'a') as f:
                f.write(' '.join(f'{ox + x * 16 + 8},{oy + y * 16 + 8}' for x, y in corners) + '\n')

main()
