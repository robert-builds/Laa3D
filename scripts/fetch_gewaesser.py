"""Messstellen an Gewaessern und im Grundwasser in der Umgebung (Hydrographischer Dienst Niederoesterreich).

Uebernommen werden nur Name, Lage, Gewaesser und die Art der Messung, keine Messwerte: Die aktuellen Werte und Warnstufen
stehen beim Land Niederoesterreich (noe.gv.at/wasserstand), die Karte verweist je Messstelle dorthin. Die Seite des Landes
erlaubt keinen Abruf aus fremden Browsern (kein CORS), und ein woechentlicher Stand waere fuer Wasserstaende wertlos.

Aufruf : python scripts/fetch_gewaesser.py   (laeuft im Wochenlauf, wenn ort.json bausteine.gewaesser gesetzt ist)
Ausgabe: site/data/gewaesser.js   window.AL_GEW = {stand, quelle, items: [{id, n, fluss, art, x, z, km, url}]}
"""
import datetime as dt, json, math, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geo import LAT0, LON0, ORT, xz  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "site", "data", "gewaesser.js")
QUELLE = "https://www.noe.gv.at/wasserstand/kidata/maplist/MapList.json"
SEITE = "https://www.noe.gv.at/wasserstand/#/de/Messstellen/Details/{id}/{p}/{g}"
ART = {"Wasserstand": "Pegel", "Durchfluss": "Pegel", "DurchflussPrognose": "Pegel", "Wassertemperatur": "Pegel", "Grundwasserspiegel": "Grundwasser"}
sys.stdout.reconfigure(encoding="utf-8")


def main():
    cfg = (ORT.get("bausteine") or {}).get("gewaesser")
    if not cfg:
        print("bausteine.gewaesser ist nicht gesetzt: nichts zu tun")
        return
    radius = float(cfg.get("radius_km") or 12)
    lat0, lon0 = ORT["geo"]["wetter_lat"], ORT["geo"]["wetter_lon"]
    req = urllib.request.Request(QUELLE, headers={"User-Agent": ORT.get("kontakt_ua") or "MyCity3D"})
    rows = json.load(urllib.request.urlopen(req, timeout=120))
    st = {}
    for r in rows:
        art = ART.get(r.get("Parameter"))
        if not art or not r.get("Lat"):
            continue
        lat, lon = float(r["Lat"]), float(r["Long"])
        km = math.hypot((lat - lat0) * 111.132, (lon - lon0) * 111.32 * math.cos(math.radians(lat0)))
        if km > radius:
            continue
        s = st.setdefault(r["Stationnumber"], {"id": r["Stationnumber"], "n": r["Stationname"], "fluss": r.get("Rivername") or "", "art": art,
                                                "km": round(km, 1), "mess": [], "url": SEITE.format(id=r["Stationnumber"], p=r.get("Linkparameter") or r["Parameter"], g=r.get("Grafik") or "3Tage")})
        x, z = xz(lat, lon)
        s["x"], s["z"] = round(x, 1), round(z, 1)
        if r["Parameter"] not in s["mess"]:
            s["mess"].append(r["Parameter"])
        if r["Parameter"] == "Wasserstand":  # Verweis bevorzugt auf die Wasserstands-Grafik
            s["url"] = SEITE.format(id=r["Stationnumber"], p="Wasserstand", g=r.get("Grafik") or "3Tage")
    items = sorted(st.values(), key=lambda s: s["km"])
    out = {"stand": dt.date.today().isoformat(), "quelle": "Hydrographischer Dienst des Landes Niederösterreich", "seite": "https://www.noe.gv.at/wasserstand/",
           "radius": radius, "items": items}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.AL_GEW=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("Messstellen im Umkreis von %.0f km: %d" % (radius, len(items)))
    for s in items:
        print("  %5.1f km  %-11s %-30s %s" % (s["km"], s["art"], s["n"], s["fluss"]))


if __name__ == "__main__":
    main()
