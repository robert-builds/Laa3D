"""Rohdaten fuer einen Ort in Oesterreich (ort.json: land.staat = "AT"). Wird von fetch.py aufgerufen, laeuft aber auch allein.

Aufruf:  python scripts/fetch_at.py <phase> [<phase> ...]
Phasen:  addr      Adressen und Gebaeudeeigenschaften der Gemeinde aus dem Adressregister (BEV, Stichtagsdaten, ZIP rund 120 MB)
         lod2      Gebaeude als Bloecke (LoD1) aus dem Digitalen Landschaftsmodell, Bauwerke (BEV, CC BY 4.0)
         dop       Luftbild: Uebersicht, je Kachel 2 m/px, bebaute Kacheln 1 m/px (basemap.at, Orthofoto, CC BY 4.0)

Quellen und Lizenzen: docs/DATENQUELLEN.md und docs/OESTERREICH.md

Gebaeude: Das BEV stellt die Bauwerke oesterreichweit als GeoPackage bereit (rund 2,6 GB). Ist das Python-Paket pyogrio
installiert (pip install pyogrio), liest das Skript ueber das Netz nur den Ausschnitt der Gemeinde (rund 20 Minuten).
Ohne pyogrio laedt es die ganze Datei einmal nach data/raw/at/ (wiederaufnehmbar) und liest sie mit sqlite3 aus der
Standardbibliothek. Koordinaten kommen in MGI / Gauss-Krueger und werden mit geo.mgi_to_latlon umgerechnet.
"""
import csv, io, json, math, os, re, sqlite3, struct, sys, time, urllib.error, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import CELL, GEMEINDE_SCHLUESSEL, LAT0, LON0, M_LAT, M_LON, ORT, UMGRENZUNG, latlon_to_mgi, mgi_to_latlon  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "gemeinde")
AT = os.path.join(RAW, "at")
CACHE = os.path.join(ROOT, "data", "raw", "at")
IMG = os.path.join(ROOT, "site", "img")
UA = ORT.get("kontakt_ua") or "MyCity3D"
ADR_URL = "https://data.bev.gv.at/download/Adressregister/Adresse_Relationale_Tabellen_Stichtagsdaten.zip"
BEV_SUCHE = "https://data.bev.gv.at/geonetwork/srv/api/search/records/_search"
WMTS = "https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg"
sys.stdout.reconfigure(encoding="utf-8")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def http(url, data=None, headers=None, timeout=300, tries=5):
    last = None
    for t in range(tries):
        try:
            h = {"User-Agent": UA}
            h.update(headers or {})
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except Exception as e:  # Timeout, Verbindungsabbruch
            last = e
        time.sleep(5 * (t + 1))
    raise RuntimeError("Abruf fehlgeschlagen: %s (%s)" % (url[:120], last))


def save(path, blob):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)


def have(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def download(url, path, min_bytes=1):
    """Grosse Datei wiederaufnehmbar laden (HTTP Range); fertige Dateien werden nicht erneut geladen."""
    if have(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    for t in range(8):
        pos = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        h = {"User-Agent": UA}
        if pos:
            h["Range"] = "bytes=%d-" % pos
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r, open(tmp, "ab" if pos and r.status == 206 else "wb") as f:
                total = pos + int(r.headers.get("Content-Length") or 0)
                last = time.time()
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
                    if time.time() - last > 30:
                        last = time.time()
                        log("  %s: %.0f von %.0f MB" % (os.path.basename(path), f.tell() / 1e6, total / 1e6))
            break
        except Exception as e:  # Abbruch: an derselben Stelle weitermachen
            log("  Unterbrechung (%s), neuer Versuch" % e)
            time.sleep(10 * (t + 1))
    if os.path.getsize(tmp) < min_bytes:
        raise RuntimeError("Download unvollstaendig: " + url)
    os.replace(tmp, path)
    return path


# ------------------------------------------------------------------ Adressregister (BEV)
EIGENSCHAFT = {"01": "wohnen", "02": "wohnen", "03": "wohnen", "04": "gewerbe", "05": "gewerbe", "06": "gewerbe",
               "07": "verkehr", "08": "industrie", "09": "oeffentlich"}  # Schnittstellenbeschreibung BEV, GEBAEUDE.csv: EIGENSCHAFT
FUNKTION = {"01": "Apotheke", "02": "Einsatzzentrale/Rettungsdienst", "03": "Polizei", "04": "Feuerwehr", "05": "Gemeindeamt",
            "06": "Krankenanstalt", "07": "Tankstelle", "08": "Schule"}


def _csv(z, name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";")


def phase_addr():
    out = os.path.join(AT, "adressen.json")
    zp = download(ADR_URL, os.path.join(CACHE, "adressregister.zip"), 50e6)
    z = zipfile.ZipFile(zp)
    stand = ""
    try:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", z.read("Aktualitaetsstand.txt").decode("latin-1"))
        stand = "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else ""
    except KeyError:
        pass
    gkz = GEMEINDE_SCHLUESSEL
    orte = {r["OKZ"]: r["ORTSNAME"] for r in _csv(z, "ORTSCHAFT.csv") if r["GKZ"] == gkz}
    strassen = {r["SKZ"]: (r["STRASSENNAME"] + (" " + r["STRASSENNAMENZUSATZ"] if r.get("STRASSENNAMENZUSATZ") and r.get("SZUSADRBEST") == "1" else ""))
                for r in _csv(z, "STRASSE.csv") if r["GKZ"] == gkz}
    adr = {}
    for r in _csv(z, "ADRESSE.csv"):
        if r["GKZ"] != gkz or not r["RW"] or not r["EPSG"]:
            continue
        lat, lon = mgi_to_latlon(float(r["RW"]), float(r["HW"]), int(r["EPSG"]))
        hn = r["HNR_ADR_ZUSAMMEN"] or r["HAUSNRTEXT"]
        s = strassen.get(r["SKZ"]) or orte.get(r["OKZ"], "")  # ohne Strasse: Ortschaft mit Hausnummer (Konskriptionsnummer)
        adr[r["ADRCD"]] = {"s": s, "n": hn, "lat": round(lat, 7), "lon": round(lon, 7), "ort": orte.get(r["OKZ"], ""), "plz": r["PLZ"], "hof": r.get("HOFNAME") or None}
    geb = {}
    for r in _csv(z, "GEBAEUDE.csv"):
        a = adr.get(r["ADRCD"])
        if not a or not r["RW"]:
            continue
        lat, lon = mgi_to_latlon(float(r["RW"]), float(r["HW"]), int(r["EPSG"]))
        g = geb.setdefault(r["OBJEKTNUMMER"], {"obj": str(int(r["OBJEKTNUMMER"])) if r["OBJEKTNUMMER"].isdigit() else r["OBJEKTNUMMER"], "lat": round(lat, 7), "lon": round(lon, 7), "u": EIGENSCHAFT.get(r.get("EIGENSCHAFT", ""), ""), "a": [], "f": []})
        g["a"].append(r["ADRCD"])
    for r in _csv(z, "GEBAEUDE_FUNKTION.csv"):
        g = geb.get(r["OBJEKTNUMMER"])
        if g and r["OBJFUNKTKENNZIFFER"] in FUNKTION and FUNKTION[r["OBJFUNKTKENNZIFFER"]] not in g["f"]:
            g["f"].append(FUNKTION[r["OBJFUNKTKENNZIFFER"]])
    save(out, json.dumps({"stand": stand, "quelle": ADR_URL, "orte": sorted(set(orte.values())), "adressen": adr, "gebaeude": list(geb.values())},
                         ensure_ascii=False).encode("utf-8"))
    log("Adressregister (Stichtag %s): %d Adressen, %d Gebaeude, Ortschaften: %s" % (stand, len(adr), len(geb), ", ".join(sorted(set(orte.values())))))


# ------------------------------------------------------------------ Bauwerke (BEV, Digitales Landschaftsmodell)
DLM_FELDER = ("HOEHE_BODEN_MEDIAN", "HOEHE_OBJEKT_MEDIAN", "HOEHE_OBJEKT_MAX", "HOEHE_OBJEKT_TRAUFE", "AGWR_OBJEKTNUMMER", "BEFLIEGUNGSJAHR", "ALS_DATUM", "F_NAME", "OBJECTID")


def dlm_url():
    """Neueste GeoPackage-Datei 'DLM Bauwerke' aus dem Katalog des BEV (Stichtag im Titel)."""
    body = {"query": {"query_string": {"query": '"Digitales Landschaftsmodell" AND Bauwerke'}}, "size": 30, "_source": ["resourceTitleObject", "link"]}
    d = json.loads(http(BEV_SUCHE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"}))
    best = None
    for h in d["hits"]["hits"]:
        for l in h["_source"].get("link") or []:
            u = (l.get("urlObject") or {}).get("default") or ""
            m = re.search(r"DLM_8000_BAUWERK_(\d{8})\.gpkg$", u)
            if m and (best is None or m.group(1) > best[0]):
                best = (m.group(1), u)
    if not best:
        raise RuntimeError("Keine GeoPackage-Datei 'DLM Bauwerke' im Katalog des BEV gefunden")
    return best


def wkb_polys(b):
    """WKB (Polygon/MultiPolygon, auch mit Z/M) -> Liste von Polygonen, je Polygon Liste von Ringen [(x, y), ...]."""
    out = []

    def rd(o):
        le = b[o] == 1
        e = "<" if le else ">"
        t = struct.unpack_from(e + "I", b, o + 1)[0]
        o += 5
        base, dims = t % 1000, 2 + (1 if t // 1000 in (1, 2) else 2 if t // 1000 == 3 else 0)
        if t & 0x80000000:
            dims += 1
        if t & 0x40000000:
            dims += 1
        base &= 0xFF
        if base == 3:
            nr = struct.unpack_from(e + "I", b, o)[0]; o += 4
            rings = []
            for _ in range(nr):
                n = struct.unpack_from(e + "I", b, o)[0]; o += 4
                v = struct.unpack_from(e + "%dd" % (n * dims), b, o); o += 8 * n * dims
                rings.append([(v[k], v[k + 1]) for k in range(0, n * dims, dims)])
            out.append(rings)
        elif base == 6:
            n = struct.unpack_from(e + "I", b, o)[0]; o += 4
            for _ in range(n):
                o = rd(o)
        return o
    rd(0)
    return out


def gpkg_wkb(blob):
    """GeoPackage-Geometrie -> WKB (Kopf mit Huelle ueberspringen)."""
    flags = blob[3]
    env = (0, 32, 48, 48, 64)[(flags >> 1) & 7]
    return blob[8 + env:]


def _bbox_mgi(epsg):
    s, w, n, e = UMGRENZUNG
    pts = [latlon_to_mgi(a, b, epsg) for a in (s, n) for b in (w, e)]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def _lesen_pyogrio(url):
    import pyogrio
    os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
    os.environ.setdefault("CPL_VSIL_CURL_CHUNK_SIZE", "1048576")
    os.environ.setdefault("GDAL_HTTP_USERAGENT", UA)
    src = "/vsicurl/" + url
    info = pyogrio.read_info(src, layer="BWK_8100_BAUWERK_F", force_feature_count=False)
    epsg = int(str(info["crs"]).split(":")[-1])
    meta, _, geom, fields = pyogrio.raw.read(src, layer="BWK_8100_BAUWERK_F", bbox=_bbox_mgi(epsg), columns=list(DLM_FELDER))
    names = list(meta["fields"])
    rows = []
    for k, g in enumerate(geom):
        if g is None:
            continue
        rows.append(({n: fields[names.index(n)][k] for n in names}, bytes(g)))
    return epsg, rows


def _lesen_sqlite(url, stichtag):
    path = download(url, os.path.join(CACHE, "DLM_8000_BAUWERK_%s.gpkg" % stichtag), 1e9)
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    srs = con.execute("SELECT srs_id FROM gpkg_geometry_columns WHERE table_name='BWK_8100_BAUWERK_F'").fetchone()[0]
    epsg = int(srs)
    x0, y0, x1, y1 = _bbox_mgi(epsg)
    sql = ("SELECT f.SHAPE, %s FROM BWK_8100_BAUWERK_F f JOIN rtree_BWK_8100_BAUWERK_F_SHAPE r ON f.OBJECTID = r.id "
           "WHERE r.maxx >= ? AND r.minx <= ? AND r.maxy >= ? AND r.miny <= ?") % ", ".join("f." + c for c in DLM_FELDER)
    try:
        cur = con.execute(sql, (x0, x1, y0, y1))
    except sqlite3.OperationalError:  # andere Spaltennamen: Geometriespalte aus dem Katalog der Datei
        gc = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name='BWK_8100_BAUWERK_F'").fetchone()[0]
        cur = con.execute(sql.replace("f.SHAPE", "f." + gc).replace("_SHAPE r", "_%s r" % gc), (x0, x1, y0, y1))
    rows = []
    for rec in cur:
        if rec[0]:
            rows.append((dict(zip(DLM_FELDER, rec[1:])), gpkg_wkb(rec[0])))
    return epsg, rows


def num(v):
    try:
        v = float(v)
        return None if math.isnan(v) else round(v, 2)
    except (TypeError, ValueError):
        return None


def phase_lod2():
    out = os.path.join(AT, "bauwerke.json")
    if have(out):
        log("Bauwerke vorhanden:", out)
        return
    stichtag, url = dlm_url()
    log("DLM Bauwerke, Stichtag %s: %s" % (stichtag, url))
    try:
        import pyogrio  # noqa: F401
        log("Lese den Ausschnitt ueber das Netz (pyogrio), das dauert rund 20 Minuten ...")
        epsg, rows = _lesen_pyogrio(url)
    except ImportError:
        log("pyogrio fehlt: lade die ganze Datei (rund 2,6 GB, einmalig). Schneller: pip install pyogrio")
        epsg, rows = _lesen_sqlite(url, stichtag)
    bw = []
    for f, wkb in rows:
        polys = []
        for rings in wkb_polys(wkb):
            polys.append([[list(map(lambda v: round(v, 7), mgi_to_latlon(x, y, epsg))) for x, y in r] for r in rings])
        if not polys:
            continue
        agwr = f.get("AGWR_OBJEKTNUMMER")
        try:
            agwr = str(int(float(agwr))) if agwr is not None and not (isinstance(agwr, float) and math.isnan(agwr)) else None
        except (TypeError, ValueError):
            agwr = None
        bw.append({"id": str(f.get("OBJECTID")), "p": polys, "hb": num(f.get("HOEHE_BODEN_MEDIAN")), "ho": num(f.get("HOEHE_OBJEKT_MEDIAN")),
                   "hx": num(f.get("HOEHE_OBJEKT_MAX")), "ht": num(f.get("HOEHE_OBJEKT_TRAUFE")), "agwr": agwr,
                   "jahr": num(f.get("BEFLIEGUNGSJAHR")), "als": f.get("ALS_DATUM") or None})
    save(out, json.dumps({"stichtag": "%s-%s-%s" % (stichtag[:4], stichtag[4:6], stichtag[6:]), "quelle": url, "bauwerke": bw}, ensure_ascii=False).encode("utf-8"))
    log("Bauwerke: %d im Rechteck der Gemeinde" % len(bw))


# ------------------------------------------------------------------ Luftbild (basemap.at, Orthofoto)
def _merc(lat, lon, z):
    n = 256 * 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def _tile(z, x, y):
    """Kachel aus dem Zwischenspeicher oder von basemap.at; None ausserhalb Oesterreichs (der Dienst antwortet dort mit 404)."""
    p = os.path.join(CACHE, "basemap", str(z), str(y), "%d.jpeg" % x)
    if not have(p):
        try:
            save(p, http(WMTS.format(z=z, x=x, y=y), timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
    return p


def getmap(bbox, w, h):
    """Luftbild fuer das Rechteck (Sued, West, Nord, Ost) in w x h Bildpunkten, linear in Grad (wie die Kacheln der Karte).
    Aus den Kacheln von basemap.at (Web-Mercator) zusammengesetzt und je Streifen von 32 Zeilen entzerrt."""
    from PIL import Image
    s, wl, n, e = bbox
    need = (e - wl) * M_LON / w  # Meter je Bildpunkt
    z = min(19, max(1, math.ceil(math.log2(156543.03 * math.cos(math.radians((s + n) / 2)) / need))))
    x0, y0 = _merc(n, wl, z)
    x1, y1 = _merc(s, e, z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    mos = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (10, 22, 38))
    jobs = [(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)]
    with ThreadPoolExecutor(6) as ex:
        for (tx, ty), p in zip(jobs, ex.map(lambda j: _tile(z, j[0], j[1]), jobs)):
            if p:  # fehlende Kachel (ausserhalb Oesterreichs) bleibt dunkel
                mos.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    ox, oy = tx0 * 256, ty0 * 256
    mesh, step = [], 32
    for r in range(0, h, step):
        r1 = min(h, r + step)
        la0, la1 = n - (n - s) * r / h, n - (n - s) * r1 / h
        ya, yb = _merc(la0, wl, z)[1] - oy, _merc(la1, wl, z)[1] - oy
        xa, xb = x0 - ox, x1 - ox
        mesh.append(((0, r, w, r1), (xa, ya, xa, yb, xb, yb, xb, ya)))
    im = mos.transform((w, h), Image.MESH, mesh, resample=Image.BICUBIC)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


if __name__ == "__main__":
    for ph in sys.argv[1:] or ["addr", "lod2"]:
        log("Phase", ph)
        globals()["phase_" + ph]()
