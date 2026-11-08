"""Digitales Geländemodell (DGM) für das Kartengebiet laden: Brandenburg (LGB) oder Österreich (BEV, ALS-Höhenraster).

Österreich (ort.json land.staat = "AT"): ALS DTM Höhenraster 1 m des BEV (CC BY 4.0), Kacheln zu 50 km in ETRS89-LAEA (EPSG:3035)
als Cloud-optimiertes GeoTIFF. Gelesen wird über das Netz nur der Ausschnitt in der Übersichtsstufe 8 m (rasterio, pip install rasterio numpy)
und auf ein Raster in lokalen Metern (10 m) umgerechnet. Ausgabe wie unten, dgm_10m.json mit "system": "lokal".


Dienst : WCS BB DGM 1m  https://isk.geobasis-bb.de/ows/dgm_wcs   (CoverageId bb_dgm, Höhen in m über NHN, Float32, GeoTIFF)
Lizenz : Datenlizenz Deutschland Namensnennung 2.0, "GeoBasis-DE/LGB, dl-de/by-2-0 (Daten geändert)"
Ausgabe: data/raw/dgm/dgm_10m.tif (EPSG:25833, 10 m je Bildpunkt, Rohdaten, nicht im Repository)
Das DGM wird landesweit etwa alle drei Jahre erneuert, ein Abruf genügt bis dahin. Aufruf: python scripts/fetch_dgm.py
"""
import json, math, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geo import LAT0, LON0, M_LAT, M_LON, STAAT, latlon_to_laea, latlon_to_utm33  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "data", "raw", "dgm")
STEP = 10  # Meter je Bildpunkt
sys.stdout.reconfigure(encoding="utf-8")


def bbox_utm():
    c = json.load(open(os.path.join(ROOT, "data", "raw", "gemeinde", "cells.json"), encoding="utf-8"))
    x0, z0, W, H = c["x0"], c["z0"], c["nx"] * c["cell"], c["nz"] * c["cell"]
    pts = []
    for fx in (0, .25, .5, .75, 1):
        for fz in (0, .25, .5, .75, 1):
            pts.append(latlon_to_utm33(LAT0 - (z0 + fz * H) / M_LAT, LON0 + (x0 + fx * W) / M_LON))
    es, ns = [p[0] for p in pts], [p[1] for p in pts]
    m = 200
    return math.floor(min(es) - m), math.floor(min(ns) - m), math.ceil(max(es) + m), math.ceil(max(ns) + m)


def als_url(e, n):
    """Neueste Kachel 'ALS DTM' des BEV für die 50-km-Kachel mit der linken unteren Ecke (e, n), über die Suche von data.gv.at."""
    import re, urllib.parse
    name = "CRS3035RES50000mN%dE%d" % (n, e)
    q = "https://www.data.gv.at/api/hub/search/search?" + urllib.parse.urlencode({"q": "ALS DTM " + name, "limit": 20})
    req = urllib.request.Request(q, headers={"User-Agent": "MyCity3D"})
    best = None
    for r in json.load(urllib.request.urlopen(req, timeout=60))["result"]["results"]:
        for d in r.get("distributions") or []:
            for u in d.get("access_url") or []:
                m = re.search(r"/ALS/DTM/(\d{8})/[^/]*" + name + r"\.tif$", u)
                if m and (best is None or m.group(1) > best[0]):
                    best = (m.group(1), u)
    if not best:
        sys.exit("Keine ALS-DTM-Kachel %s bei data.gv.at gefunden" % name)
    return best


def main_at():
    """Österreich: Geländehöhen aus dem ALS DTM des BEV, direkt im lokalen Raster der Karte (x Ost, z Süd, 10 m)."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    os.makedirs(OUT, exist_ok=True)
    c = json.load(open(os.path.join(ROOT, "data", "raw", "gemeinde", "cells.json"), encoding="utf-8"))
    x0, z0, W, H = c["x0"], c["z0"], c["nx"] * c["cell"], c["nz"] * c["cell"]
    w, h = int(W / STEP), int(H / STEP)
    xs = x0 + (np.arange(w) + 0.5) * STEP
    zs = z0 + (np.arange(h) + 0.5) * STEP
    lat = LAT0 - zs / M_LAT
    lon = LON0 + xs / M_LON
    E = np.zeros((h, w)); N = np.zeros((h, w))
    for r in range(h):  # Umrechnung je Bildpunkt (reine Python-Formel, 10 m Raster: wenige Sekunden)
        for q in range(w):
            E[r, q], N[r, q] = latlon_to_laea(lat[r], lon[q])
    out = np.full((h, w), -9999.0, dtype=np.float32)
    os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    quellen = []
    for te in range(int(E.min() // 50000) * 50000, int(E.max() // 50000) * 50000 + 1, 50000):
        for tn in range(int(N.min() // 50000) * 50000, int(N.max() // 50000) * 50000 + 1, 50000):
            datum, url = als_url(te, tn)
            quellen.append(url)
            print("ALS DTM %s (Stichtag %s)" % (url, datum))
            with rasterio.open("/vsicurl/" + url) as ds:
                m = (E >= te) & (E < te + 50000) & (N >= tn) & (N < tn + 50000)
                if not m.any():
                    continue
                e0, e1, n0, n1 = E[m].min() - 20, E[m].max() + 20, N[m].min() - 20, N[m].max() + 20
                win = from_bounds(e0, n0, e1, n1, ds.transform).round_offsets().round_lengths()
                fac = 8  # Übersichtsstufe 8 m: GDAL liest nur diese
                shp = (max(2, int(win.height / fac)), max(2, int(win.width / fac)))
                a = ds.read(1, window=win, out_shape=shp, resampling=rasterio.enums.Resampling.average).astype(np.float64)
                a[a <= -9000] = np.nan
                wt = ds.window_transform(win)
                ce = (E[m] - wt.c) / (wt.a * win.width / shp[1]) - 0.5
                rn = (N[m] - wt.f) / (wt.e * win.height / shp[0]) - 0.5
                c0 = np.clip(np.floor(ce).astype(int), 0, shp[1] - 2); r0 = np.clip(np.floor(rn).astype(int), 0, shp[0] - 2)
                fc, fr = np.clip(ce - c0, 0, 1), np.clip(rn - r0, 0, 1)
                v = a[r0, c0] * (1 - fc) * (1 - fr) + a[r0, c0 + 1] * fc * (1 - fr) + a[r0 + 1, c0] * (1 - fc) * fr + a[r0 + 1, c0 + 1] * fc * fr
                out[m] = np.where(np.isfinite(v), v, -9999.0)
    from PIL import Image
    p = os.path.join(OUT, "dgm_10m.tif")
    Image.fromarray(out, "F").save(p)
    with open(os.path.join(OUT, "dgm_10m.json"), "w", encoding="utf-8") as f:
        json.dump({"system": "lokal", "x0": x0, "z0": z0, "w": w, "h": h, "step": STEP, "gelesen": __import__("datetime").date.today().isoformat(),
                   "quelle": "ALS DTM Höhenraster 1 m, BEV, CC BY 4.0: " + ", ".join(quellen), "hoehenbezug": "m ü. A."}, f, ensure_ascii=False)
    ok = out > -9000
    print("gespeichert: %s, %d x %d, Höhe %.0f bis %.0f m ü. A." % (p, w, h, out[ok].min(), out[ok].max()))


def main():
    if STAAT == "AT":
        return main_at()
    os.makedirs(OUT, exist_ok=True)
    e0, n0, e1, n1 = bbox_utm()
    w, h = (e1 - e0) // STEP, (n1 - n0) // STEP
    e1, n1 = e0 + w * STEP, n0 + h * STEP
    url = ("https://isk.geobasis-bb.de/ows/dgm_wcs?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&COVERAGEID=bb_dgm&FORMAT=image/tiff"
           "&SUBSET=x(%d,%d)&SUBSET=y(%d,%d)&SCALESIZE=x(%d),y(%d)" % (e0, e1, n0, n1, w, h))
    print("Abruf %d x %d Bildpunkte, E %d-%d, N %d-%d" % (w, h, e0, e1, n0, n1))
    with urllib.request.urlopen(url, timeout=600) as r:
        blob = r.read()
    p = os.path.join(OUT, "dgm_10m.tif")
    with open(p, "wb") as f:
        f.write(blob)
    with open(os.path.join(OUT, "dgm_10m.json"), "w", encoding="utf-8") as f:
        json.dump({"e0": e0, "n0": n0, "e1": e1, "n1": n1, "w": w, "h": h, "step": STEP, "gelesen": __import__("datetime").date.today().isoformat(),
                   "quelle": "WCS BB DGM 1m, GeoBasis-DE/LGB, dl-de/by-2-0"}, f)
    print("gespeichert:", p, "%.1f MB" % (len(blob) / 1e6))


if __name__ == "__main__":
    main()
