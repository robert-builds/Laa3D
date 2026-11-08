"""Triangulation (Ear-Clipping) fuer 3D-Polygone der Gebaeude. Nur Standardbibliothek.

Aus dem ersten Prototyp herausgeloest, weil prepare_gemeinde.py nur diese Funktion braucht.
"""
import math


# ---------------------------------------------------------------- Triangulation
def newell(pts):
    nx = ny = nz = 0.0
    for i in range(len(pts)):
        x1, y1, z1 = pts[i]
        x2, y2, z2 = pts[(i + 1) % len(pts)]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / ln, ny / ln, nz / ln


def tri_area2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def in_tri(p, a, b, c):
    d1 = tri_area2(p, a, b)
    d2 = tri_area2(p, b, c)
    d3 = tri_area2(p, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def ear_clip(p2):
    n = len(p2)
    if n < 3:
        return []
    area = sum(tri_area2((0, 0), p2[i], p2[(i + 1) % n]) for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]
    out = []
    guard = 0
    while len(idx) > 3 and guard < 4 * n * n:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = p2[i0], p2[i1], p2[i2]
            if tri_area2(a, b, c) <= 1e-9:
                continue
            if any(in_tri(p2[j], a, b, c) for j in idx if j not in (i0, i1, i2) and p2[j] not in (a, b, c)):  # gleiche Punkte (Bruecke zu einem Loch) zaehlen nicht
                continue
            out.append((i0, i1, i2))
            del idx[k]
            clipped = True
            break
        if not clipped:
            break
    if len(idx) == 3:
        out.append((idx[0], idx[1], idx[2]))
    return out


def triangulate(pts):
    nx, ny, nz = newell(pts)
    ax = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
    keep = [i for i in range(3) if i != ax]
    p2 = [(p[keep[0]], p[keep[1]]) for p in pts]
    return ear_clip(p2), (nx, ny, nz)




def _seg_cross(a, b, c, d):
    """Schneiden sich die Strecken a-b und c-d echt (ohne gemeinsame Endpunkte)?"""
    if a in (c, d) or b in (c, d):
        return False
    d1, d2 = tri_area2(c, d, a), tri_area2(c, d, b)
    d3, d4 = tri_area2(a, b, c), tri_area2(a, b, d)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0)


def triangulate_holes(outer, holes):
    """Ebenes Polygon mit Loechern (Innenhoefe) triangulieren: jedes Loch wird ueber eine Bruecke zum naechsten sichtbaren
    Punkt des aeusseren Rings angehaengt, dann Ear-Clipping. Gibt (Punkte, Dreiecke) zurueck; Punkte = 2D-Liste (x, z)."""
    def area(r):
        return sum(tri_area2((0, 0), r[i], r[(i + 1) % len(r)]) for i in range(len(r)))
    poly = list(outer) if area(outer) > 0 else list(outer)[::-1]
    for h in sorted([list(h) for h in holes if len(h) >= 3], key=lambda h: -max(p[0] for p in h)):
        h = h if area(h) < 0 else h[::-1]  # Loch entgegen dem aeusseren Ring
        hi = max(range(len(h)), key=lambda i: h[i][0])
        hp = h[hi]
        edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        best = None
        for k in sorted(range(len(poly)), key=lambda k: (poly[k][0] - hp[0]) ** 2 + (poly[k][1] - hp[1]) ** 2):
            if not any(_seg_cross(hp, poly[k], a, b) for a, b in edges):
                best = k
                break
        if best is None:
            continue
        ring = h[hi:] + h[:hi] + [h[hi]]
        poly = poly[:best + 1] + ring + [poly[best]] + poly[best + 1:]
    return poly, ear_clip(poly)
