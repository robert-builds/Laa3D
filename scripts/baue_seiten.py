"""Baut index.html, karte.html und data/ort.js aus vorlage/ und ort.json.

Aufruf: python scripts/baue_seiten.py
Die Seiten in site/ werden bei jedem Lauf neu erzeugt. Nicht von Hand in site/index.html oder
site/karte.html aendern, sondern in vorlage/ oder in ort.json.
"""
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import LAT0, LON0, ORT, ROOT, STAAT  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def grad(v, pos, neg):
    return ("%.2f" % abs(v)).replace(".", ",") + "° " + (pos if v >= 0 else neg)


def werte():
    nb = ORT.get("nachbarort")
    fp = ORT["fahrplan"]
    art = ORT.get("art", "Gemeinde")
    return {
        "NAME": ORT["name"],
        "ART": art,
        "UNTERTITEL": ORT.get("untertitel", "Karte der " + art),
        "BESCHREIBUNG": ORT.get("kurzbeschreibung", ""),
        "KOORD": grad(LAT0, "N", "S") + " · " + grad(LON0, "O", "W"),
        "NB_NAME": nb["name"] if nb else "Nachbarort",
        "CSP": csp(),
        "BETREIBER": fp["betreiber"],
        "BETREIBER_KURZ": fp.get("betreiber_kurz", fp["betreiber"]),
        "FAHRPLAN_LIZENZ": fp["lizenz"],
        "GEO_QUELLE": "© BEV, CC BY 4.0 (Daten geändert) · © Österreichisches Adressregister · basemap.at" if STAAT == "AT" else "© GeoBasis-DE/LGB, dl-de/by-2-0 (Daten geändert)",
        "LANG": "de-AT" if STAAT == "AT" else "de",
        "GEB_TEXT": ("als Blöcke aus Grundriss und Laserscan-Höhe auf dem Luftbild. Einfärben nach Nutzung, Höhe oder Dachfarbe." if STAAT == "AT"
                     else "mit Dachformen auf dem aktuellen Luftbild. Einfärben nach Nutzung, Höhe oder Bodenrichtwert."),
        "STAND_TEXT": ("Gebäude und Adressen ändern sich seltener und werden mit den Stichtagsdaten des BEV nachgezogen." if STAAT == "AT"
                       else "Gebäude, Adressen und Bodenrichtwerte ändern sich seltener und werden nur bei neuen Veröffentlichungen der Landesvermessung nachgezogen."),
        "HTML_KARTEN": karten_extra(),
        "LAGE_TEXT": "Luftqualität und Müllabfuhr." if STAAT == "AT" else "Warnungen, Luft, Baustellen und Störungen.",
    }


def karten_extra():
    """Zusätzliche Karten der Startseite für eingeschaltete Bausteine (rohes HTML, feste Texte)."""
    b = bausteine()
    out = ""
    if b["verordnungen"]:
        out += ('\n      <article class="card3"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3v4a1 1 0 0 0 1 1h4"></path><path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>'
                '\n        <h3>Verordnungen</h3><p>Verkehrsverordnungen der Bezirkshauptmannschaft und Verordnungen der Gemeinde aus data.gv.at, mit Verweis auf das amtliche Dokument und Ort auf der Karte.</p></article>')
    if b["gewaesser"]:
        out += ('\n      <article class="card3"><svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"></path><path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"></path><path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"></path></svg>'
                '\n        <h3>Thaya und Grundwasser</h3><p>Pegel und Grundwasser-Messstellen in der Umgebung, mit Sprung zu den aktuellen Werten des Landes.</p></article>')
    return out


def bausteine():
    """Optionale Bausteine aus ort.json (Abschnitt "bausteine"); fehlt der Abschnitt, sind alle aus."""
    b = ORT.get("bausteine") or {}
    m = b.get("muellabfuhr")
    return {"baustellen": bool(b.get("baustellen")), "gelaende": bool(b.get("gelaende")), "muell": m if (m and m.get("url")) else None,
            "brw": STAAT == "DE" and b.get("bodenrichtwerte", True) is not False, "verordnungen": bool(b.get("verordnungen")), "gewaesser": bool(b.get("gewaesser"))}


def csp():
    """Inhaltsrichtlinie (Content-Security-Policy) als meta-Tag: nur eigene Dateien, Verbindungen nur zu den Diensten, die ort.json einschaltet."""
    fp = ORT["fahrplan"]
    b = bausteine()
    if STAAT == "AT":  # Wetter: GeoSphere Austria (Messung, Warnungen) und Open-Meteo (Vorhersage)
        connect = ["'self'", "https://dataset.api.hub.geosphere.at", "https://warnungen.zamg.at", "https://api.open-meteo.com", "https://air-quality-api.open-meteo.com"]
    else:
        connect = ["'self'", "https://api.brightsky.dev", "https://air-quality-api.open-meteo.com"]
    if b["baustellen"]:
        connect.append("https://isk.geobasis-bb.de")
    if not fp.get("live_aus"):
        connect += fp.get("live_hosts", [])
    s = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src "
         + " ".join(connect))
    if b["muell"]:
        m = re.match(r"(https?://[^/]+)", b["muell"]["url"])
        if m:
            s += "; frame-src " + m.group(1)
    return s + "; object-src 'none'; base-uri 'self'; form-action 'self'"


def ort_js():
    nb = ORT.get("nachbarort")
    fp = ORT["fahrplan"]
    v = ORT.get("veroeffentlichung", {})
    b = bausteine()
    o = {
        "name": ORT["name"], "art": ORT.get("art", "Gemeinde"), "land": ORT["land"]["name"],
        "nb": nb["name"] if nb else None,
        "wetter": [ORT["geo"]["wetter_lat"], ORT["geo"]["wetter_lon"]],
        "umgrenzung": ORT["geo"]["umgrenzung_sued_west_nord_ost"],
        "ortsteileSeite": ORT.get("ortsteile_seite", ""),
        "betreiber": fp["betreiber"], "betreiberKurz": fp.get("betreiber_kurz", fp["betreiber"]),
        "lizenz": fp["lizenz"], "lizenzUrl": fp.get("lizenz_url", ""),
        "liveHosts": [] if fp.get("live_aus") else fp.get("live_hosts", []),
        "impressum": v.get("impressum_url", ""), "datenschutz": v.get("datenschutz_url", ""),
        "baustellen": b["baustellen"], "gelaende": b["gelaende"], "muell": b["muell"],
        "solarKwh": (ORT.get("bausteine") or {}).get("solar_kwh_je_kwp"), "betreiberKuerzel": fp.get("betreiber_kuerzel", {}),
        "staat": STAAT, "zeitzone": ORT.get("zeitzone") or ("Europe/Vienna" if STAAT == "AT" else "Europe/Berlin"),
        "hoehe": "m ü. A." if STAAT == "AT" else "m über NHN", "brw": b["brw"], "verordnungen": b["verordnungen"], "gewaesser": b["gewaesser"],
        "landName": ORT["land"]["name"], "gkz": ORT["geo"]["gemeindeschluessel"],
        "wetterStation": ORT["geo"].get("wetter_station"), "wetterStationName": ORT["geo"].get("wetter_station_name"),
    }
    return "window.ORT = " + json.dumps(o, ensure_ascii=False) + ";\n"


def main():
    w = werte()
    vor = os.path.join(ROOT, "vorlage")
    site = os.path.join(ROOT, "site")
    for name in ("index.html", "karte.html"):
        s = open(os.path.join(vor, name), encoding="utf-8").read()
        s = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: w[m.group(1)] if m.group(1).startswith("HTML_") else html.escape(w[m.group(1)], quote=True), s)
        rest = re.findall(r"\{\{[A-Z_]+\}\}", s)
        if rest:
            sys.exit("Unersetzte Platzhalter in %s: %s" % (name, rest))
        open(os.path.join(site, name), "w", encoding="utf-8", newline="\n").write(s)
        print("geschrieben:", name)
    os.makedirs(os.path.join(site, "data"), exist_ok=True)
    open(os.path.join(site, "data", "ort.js"), "w", encoding="utf-8", newline="\n").write(ort_js())
    print("geschrieben: data/ort.js")
    for fn, var in (("brw.js", "window.AL_BRW=null;"), ("verordnungen.js", "window.AL_VO=null;"), ("gewaesser.js", "window.AL_GEW=null;")):
        p = os.path.join(site, "data", fn)  # optionale Daten: leerer Platzhalter, damit die Seite ohne sie laeuft
        if not os.path.exists(p):
            open(p, "w", encoding="utf-8", newline="\n").write(var + "\n")
            print("geschrieben: data/%s (leer)" % fn)
    ev = os.path.join(site, "data", "events_auto.js")  # Platzhalter, solange kein Termin-Abruf eingerichtet ist
    if not os.path.exists(ev):
        open(ev, "w", encoding="utf-8", newline="\n").write('window.AL_EVENTS_AUTO={"stand":null,"quellen":[],"items":[]};\n')
        print("geschrieben: data/events_auto.js (leer)")


if __name__ == "__main__":
    main()
