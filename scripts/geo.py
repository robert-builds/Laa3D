"""Gemeinsame Geometrie-Helfer (nur Standardbibliothek).

Lokales Koordinatensystem: x = Ost [m], z = -Nord [m], Ursprung LAT0/LON0.
Die Abbildung ist linear in Grad. Ein Kachelrechteck in Metern entspricht deshalb genau
einem Breiten-/Laengen-Rechteck (wichtig fuer die Luftbild-Abrufe).
"""
import math

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lade_ort():
    """Liest ort.json aus dem Projektordner (einzige Stelle mit Ortsangaben)."""
    with open(os.path.join(ROOT, "ort.json"), encoding="utf-8") as f:
        return json.load(f)


ORT = lade_ort()
_G = ORT["geo"]
LAT0, LON0 = _G["lat0"], _G["lon0"]
M_LAT = 111132.0
M_LON = 111320.0 * math.cos(math.radians(LAT0))
CELL = float(_G["kachel_m"])  # Kantenlaenge einer Kachel in Metern
GEMEINDE_RELATION = int(_G["osm_relation"])  # OSM-Relation der Gemeindegrenze
GEMEINDE_SCHLUESSEL = str(_G["gemeindeschluessel"])  # amtlicher Gemeindeschluessel (DE: AGS, 8 Stellen; AT: Gemeindekennziffer, 5 Stellen)
STAAT = (ORT.get("land") or {}).get("staat", "DE")  # "DE" oder "AT": waehlt die Geodienste (Brandenburg bzw. Oesterreich)
OT_ADMIN_LEVEL = int(_G.get("ortsteile_admin_level", 9))  # OSM-Ebene der Ortsteile (Brandenburg 9, Oesterreich: Katastralgemeinden 10)
ORT_NAME = ORT["name"]
UMGRENZUNG = tuple(_G["umgrenzung_sued_west_nord_ost"])  # grobe Umgrenzung fuer Abfragen (Sued, West, Nord, Ost)

# Optionaler Nachbarort, schlank mit aufgenommen (Orte, Haltestellen, Gebaeude, Luftbild der Kachel).
# In ort.json "nachbarort": null -> kein Nachbarort; in_nb() liefert dann immer False.
_NB = ORT.get("nachbarort")
NB_NAME = _NB["name"] if _NB else None
NB_BBOX = tuple(_NB["bbox_sued_west_nord_ost"]) if _NB else (0.0, 0.0, 0.0, 0.0)
NB_CENTER = tuple(_NB["mitte_lat_lon"]) if _NB else None


def in_nb(x, z):
    """Liegt der Punkt (lokale Meter) im Rechteck des Nachbarorts?"""
    if not _NB:
        return False
    lat, lon = LAT0 - z / M_LAT, LON0 + x / M_LON
    return NB_BBOX[0] <= lat <= NB_BBOX[2] and NB_BBOX[1] <= lon <= NB_BBOX[3]


def xz(lat, lon):
    return ((lon - LON0) * M_LON, -(lat - LAT0) * M_LAT)


def latlon(x, z):
    return (LAT0 - z / M_LAT, LON0 + x / M_LON)


def utm33_to_latlon(E, N):
    """ETRS89 / UTM 33N (EPSG:25833) -> Breite/Laenge in Grad (Krueger-Reihe, Fehler im mm-Bereich)."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    beta = [n / 2 - 2 * n ** 2 / 3 + 37 * n ** 3 / 96, n ** 2 / 48 + n ** 3 / 15, 17 * n ** 3 / 480]
    delta = [2 * n - 2 * n ** 2 / 3 - 2 * n ** 3, 7 * n ** 2 / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15]
    xi = N / (k0 * A)
    eta = (E - 500000.0) / (k0 * A)
    xi_p = xi - sum(beta[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_p = eta - sum(beta[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi + sum(delta[j] * math.sin(2 * (j + 1) * chi) for j in range(3))
    lon = math.radians(15.0) + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lat), math.degrees(lon)


def latlon_to_utm33(lat, lon):
    """Breite/Laenge in Grad -> ETRS89 / UTM 33N (EPSG:25833), Krueger-Reihe (Gegenstueck zu utm33_to_latlon)."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    alpha = [n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240]
    phi, dl = math.radians(lat), math.radians(lon - 15.0)
    q = 2 * math.sqrt(n) / (1 + n)
    t = math.sinh(math.atanh(math.sin(phi)) - q * math.atanh(q * math.sin(phi)))
    xi_p = math.atan2(t, math.cos(dl))
    eta_p = math.atanh(math.sin(dl) / math.sqrt(1 + t * t))
    xi = xi_p + sum(alpha[j] * math.sin(2 * (j + 1) * xi_p) * math.cosh(2 * (j + 1) * eta_p) for j in range(3))
    eta = eta_p + sum(alpha[j] * math.cos(2 * (j + 1) * xi_p) * math.sinh(2 * (j + 1) * eta_p) for j in range(3))
    return 500000.0 + k0 * A * eta, k0 * A * xi


# ------------------------------------------------------------------ Oesterreich: MGI (Gauss-Krueger) und ETRS89-LAEA (EPSG:3035)
_BESSEL = (6377397.155, 1 / 299.1528128)
_GRS80 = (6378137.0, 1 / 298.257222101)
_MGI_L0 = {31254: 10 + 1 / 3, 31255: 13 + 1 / 3, 31256: 16 + 1 / 3}  # MGI / Austria GK West, Central, East


def _tm_inverse(E, N, lon0, a, f, fn=0.0):
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    beta = [n / 2 - 2 * n ** 2 / 3 + 37 * n ** 3 / 96, n ** 2 / 48 + n ** 3 / 15, 17 * n ** 3 / 480]
    delta = [2 * n - 2 * n ** 2 / 3 - 2 * n ** 3, 7 * n ** 2 / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15]
    xi, eta = (N - fn) / A, E / A
    xi_p = xi - sum(beta[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_p = eta - sum(beta[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    return chi + sum(delta[j] * math.sin(2 * (j + 1) * chi) for j in range(3)), math.radians(lon0) + math.atan2(math.sinh(eta_p), math.cos(xi_p))


def _ecef(lat, lon, a, f):
    e2 = f * (2 - f)
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return N * math.cos(lat) * math.cos(lon), N * math.cos(lat) * math.sin(lon), N * (1 - e2) * math.sin(lat)


def _geodetic(X, Y, Z, a, f):
    e2 = f * (2 - f)
    p, lon = math.hypot(X, Y), math.atan2(Y, X)
    lat = math.atan2(Z, p * (1 - e2))
    for _ in range(6):
        lat = math.atan2(Z + e2 * a / math.sqrt(1 - e2 * math.sin(lat) ** 2) * math.sin(lat), p)
    return lat, lon


def mgi_to_latlon(E, N, epsg):
    """MGI / Austria GK (EPSG 31254, 31255, 31256) -> WGS84/ETRS89 in Grad.
    Datumsuebergang mit den 7 Parametern des BEV (MGI -> ETRS89), Abweichung im Bereich weniger Dezimeter;
    fuer die Karte genau genug (geprueft gegen PROJ, Abweichung unter 1 mm zur PROJ-Standardumrechnung)."""
    lat, lon = _tm_inverse(E, N, _MGI_L0[int(epsg)], *_BESSEL, fn=-5000000.0)
    X, Y, Z = _ecef(lat, lon, *_BESSEL)
    s = math.pi / 180 / 3600
    tx, ty, tz, rx, ry, rz, ds = 577.326, 90.129, 463.919, 5.137 * s, 1.474 * s, 5.297 * s, 2.4232e-6
    X2 = tx + (1 + ds) * (X - rz * Y + ry * Z)
    Y2 = ty + (1 + ds) * (rz * X + Y - rx * Z)
    Z2 = tz + (1 + ds) * (-ry * X + rx * Y + Z)
    la, lo = _geodetic(X2, Y2, Z2, *_GRS80)
    return math.degrees(la), math.degrees(lo)


def latlon_to_mgi(lat, lon, epsg):
    """Gegenstueck zu mgi_to_latlon (iterativ, fuer Abfrage-Rechtecke)."""
    lo0 = _MGI_L0[int(epsg)]
    E, N = (lon - lo0) * 111320.0 * math.cos(math.radians(lat)), lat * 111132.0 - 5000000.0
    for _ in range(8):
        la, lo = mgi_to_latlon(E, N, epsg)
        E += (lon - lo) * 111320.0 * math.cos(math.radians(lat))
        N += (lat - la) * 111132.0
    return E, N


def latlon_to_laea(lat, lon):
    """ETRS89 Breite/Laenge -> ETRS89-LAEA Europa (EPSG:3035), Rechtswert und Hochwert in Metern."""
    a, f = _GRS80
    e2 = f * (2 - f); e = math.sqrt(e2)
    q = lambda ph: (1 - e2) * (math.sin(ph) / (1 - e2 * math.sin(ph) ** 2) - math.log((1 - e * math.sin(ph)) / (1 + e * math.sin(ph))) / (2 * e))
    qp = q(math.pi / 2)
    ph0, l0 = math.radians(52.0), math.radians(10.0)
    ph, lm = math.radians(lat), math.radians(lon)
    b, b0 = math.asin(q(ph) / qp), math.asin(q(ph0) / qp)
    Rq = a * math.sqrt(qp / 2)
    D = a * (math.cos(ph0) / math.sqrt(1 - e2 * math.sin(ph0) ** 2)) / (Rq * math.cos(b0))
    B = Rq * math.sqrt(2 / (1 + math.sin(b0) * math.sin(b) + math.cos(b0) * math.cos(b) * math.cos(lm - l0)))
    x = B * D * math.cos(b) * math.sin(lm - l0)
    y = (B / D) * (math.cos(b0) * math.sin(b) - math.sin(b0) * math.cos(b) * math.cos(lm - l0))
    return 4321000.0 + x, 3210000.0 + y


def pip(x, z, ring):
    """Punkt-in-Polygon (Strahlverfahren); ring = [(x,z),...]."""
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, zi = ring[i]
        xj, zj = ring[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            c = not c
        j = i
    return c


def stitch(parts):
    """Setzt Linienstuecke (Listen von (a,b)-Punkten) an gleichen Endpunkten zu Ringen zusammen."""
    parts = [list(p) for p in parts if len(p) >= 2]
    rings = []
    while parts:
        cur = parts.pop(0)
        grown = True
        while grown and cur[0] != cur[-1]:
            grown = False
            for k, p in enumerate(parts):
                if p[0] == cur[-1]:
                    cur += p[1:]
                elif p[-1] == cur[-1]:
                    cur += p[::-1][1:]
                elif p[-1] == cur[0]:
                    cur = p[:-1] + cur
                elif p[0] == cur[0]:
                    cur = p[::-1][:-1] + cur
                else:
                    continue
                parts.pop(k)
                grown = True
                break
        if len(cur) >= 4 and cur[0] == cur[-1]:
            rings.append(cur)
    return rings


def simplify(pts, tol):
    """Douglas-Peucker (iterativ) fuer Punktlisten [(x,z),...].

    Geschlossene Ringe (Anfang gleich Ende) werden am weitesten Punkt geteilt und je Haelfte
    vereinfacht. Sonst ist die Grundlinie Anfang-Ende ein Punkt, alle Abstaende werden 0 und
    vom ganzen Ring bleiben zwei Punkte uebrig."""
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1] and len(pts) > 3:
        k = max(range(1, len(pts) - 1), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
        return simplify(pts[:k + 1], tol)[:-1] + simplify(pts[k:], tol)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        (x1, z1), (x2, z2) = pts[s], pts[e]
        dx, dz = x2 - x1, z2 - z1
        dd = math.hypot(dx, dz) or 1e-9
        best, bi = 0.0, -1
        for i in range(s + 1, e):
            d = abs(dz * (pts[i][0] - x1) - dx * (pts[i][1] - z1)) / dd
            if d > best:
                best, bi = d, i
        if best > tol and bi > 0:
            keep[bi] = True
            stack += [(s, bi), (bi, e)]
    return [p for p, k in zip(pts, keep) if k]
