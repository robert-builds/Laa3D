"""Baut index.html, karte.html, touren.html und data/ort.js aus vorlage/ und ort.json.

Aufruf: python scripts/baue_seiten.py
Die Seiten in site/ werden bei jedem Lauf neu erzeugt. Nicht von Hand in site/index.html, site/karte.html oder
site/touren.html aendern, sondern in vorlage/ oder in ort.json.

Vorlagen: {{NAME}} und weitere Platzhalter werden ersetzt (Werte HTML-geschuetzt, Namen auf _HTML enthalten fertiges HTML).
Bedingte Teile: <!--IF baustein--> ... <!--ENDIF--> bleibt nur stehen, wenn ort.json den Baustein einschaltet
(Liste der Namen: features()). Bloecke duerfen verschachtelt sein.
"""
import html
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import LAT0, LON0, ORT, ROOT, STAAT  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

SEITEN = ("index.html", "karte.html", "touren.html")


def grad(v, pos, neg):
    return ("%.2f" % abs(v)).replace(".", ",") + "° " + (pos if v >= 0 else neg)


def bausteine():
    """Optionale Bausteine aus ort.json (Abschnitt "bausteine"); fehlt der Abschnitt, sind alle aus."""
    b = ORT.get("bausteine") or {}
    m = b.get("muellabfuhr")
    wb = b.get("waldbrand") or {}
    mp = b.get("meldeportal") or {}
    cam = b.get("webcam") or {}
    kl = b.get("klima") or {}
    return {
        "baustellen": bool(b.get("baustellen")),
        "gelaende": bool(b.get("gelaende")),
        "muell": m if (m and m.get("url")) else None,
        "bodenfeuchte": bool(b.get("landwirtschaft")),
        "waldbrand": wb if wb.get("kreis") else None,
        "meldeportal": mp if mp.get("url") else None,
        "drohne": bool(b.get("drohnenhinweis")),
        "notfall": bool(b.get("notfall")),
        "klima": bool(kl.get("stationen")),
        "geschichte": bool(b.get("ortsgeschichte")),
        "touren": bool(b.get("touren")),
        "webcam": cam if cam.get("url") else None,
        "brw": STAAT == "DE" and b.get("bodenrichtwerte", True) is not False,  # Bodenrichtwerte (BORIS) nur Brandenburg
        "verordnungen": bool(b.get("verordnungen")),  # Oesterreich: data.gv.at
        "gewaesser": bool(b.get("gewaesser")),  # Niederoesterreich: Messstellen des Landes
        "at": STAAT == "AT",
    }


def features():
    """Namen fuer <!--IF name--> in den Vorlagen."""
    b = bausteine()
    f = {k: bool(v) for k, v in b.items()}
    f["ebenen"] = f["notfall"] or f["gelaende"] or f["touren"]  # Rubrik "Landwirtschaft und Sicherheit" bei den Ebenen
    f["landwirt"] = f["bodenfeuchte"] or f["waldbrand"] or f["meldeportal"] or f["drohne"]  # Rubrik "Landwirtschaft und Sicherheit"
    return f


def optionale_dateien():
    """Dateien in site/, die zu den eingeschalteten Bausteinen gehoeren (fuer pruefe_veroeffentlichung.py)."""
    f = features()
    out = []
    if f["gelaende"]:
        out += ["img/relief.png", "img/hang.png", "img/senken.png"]
    if f["landwirt"]:
        out += ["landwirt.js", "start_landwirt.js"]
    if f["bodenfeuchte"]:
        out += ["data/landwirt.js"]
    if f["waldbrand"]:
        out += ["data/waldbrand.js"]
    if f["klima"]:
        out += ["klima.js", "start_klima.js", "data/klima.js"]
    if f["notfall"]:
        out += ["data/notfall.js"]
    if f["geschichte"]:
        out += ["data/ortsgeschichte.js"]
    if f["touren"]:
        out += ["touren.html", "touren.js", "data/touren.js"]
    if f["verordnungen"]:
        out += ["data/verordnungen.js"]
    if f["gewaesser"]:
        out += ["data/gewaesser.js"]
    return out


# Datendateien, die die Seiten laden: bis das jeweilige Skript sie erzeugt hat, steht ein leerer Platzhalter da (kein 404)
PLATZHALTER = {
    "landwirt.js": "AL_LANDW", "waldbrand.js": "AL_WALDBRAND", "klima.js": "AL_KLIMA",
    "notfall.js": "AL_NOTFALL", "ortsgeschichte.js": "AL_GESCHICHTE", "touren.js": "AL_TOUREN",
    "brw.js": "AL_BRW", "verordnungen.js": "AL_VO", "gewaesser.js": "AL_GEW",
}
# Welcher Baustein (features()) zu welcher Datendatei gehoert: ist er aus, wird die Datei auf den leeren Platzhalter
# zurueckgesetzt, damit Daten eines frueheren Laufs (z. B. eines anderen Orts oder Landes) nicht weiter angezeigt werden.
DATEN_BAUSTEIN = {
    "landwirt.js": "bodenfeuchte", "waldbrand.js": "waldbrand", "klima.js": "klima", "notfall.js": "notfall",
    "ortsgeschichte.js": "geschichte", "touren.js": "touren", "brw.js": "brw", "verordnungen.js": "verordnungen", "gewaesser.js": "gewaesser",
}


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
    img = "'self' data: blob:"
    if b["webcam"]:
        u = urlparse(b["webcam"]["url"])
        img += " %s://%s" % (u.scheme, u.netloc)
    s = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src " + img + "; font-src 'self'; connect-src "
         + " ".join(connect))
    if b["muell"]:
        m = re.match(r"(https?://[^/]+)", b["muell"]["url"])
        if m:
            s += "; frame-src " + m.group(1)
    return s + "; object-src 'none'; base-uri 'self'; form-action 'self'"


def urheber():
    """Optionale Urheberzeile (ort.json: veroeffentlichung.urheber = {name, link_text, link_url}); leer = keine Zeile."""
    u = (ORT.get("veroeffentlichung") or {}).get("urheber") or {}
    name = (u.get("name") or "").strip()
    if not name:
        return "", ""
    link = ""
    if u.get("link_url") and u.get("link_text"):
        link = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (html.escape(u["link_url"], quote=True), html.escape(u["link_text"]))
    n = html.escape(name)
    zeile = '<p class="credit">Idee und Umsetzung: %s%s</p>' % (n, (" · " + link) if link else "")
    attr = " · Idee und Umsetzung: %s%s" % (n, (" (" + link + ")") if link else "")
    return zeile, attr


def werte():
    nb = ORT.get("nachbarort")
    fp = ORT["fahrplan"]
    art = ORT.get("art", "Gemeinde")
    b = bausteine()
    zeile, attr = urheber()
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
        "MELDEPORTAL_NAME": (b["meldeportal"] or {}).get("name", ""),
        "URHEBER_ZEILE_HTML": zeile,
        "URHEBER_ATTR_HTML": attr,
        "GEO_QUELLE": "© BEV, CC BY 4.0 (Daten geändert) · © Österreichisches Adressregister · basemap.at" if STAAT == "AT" else "© GeoBasis-DE/LGB, dl-de/by-2-0 (Daten geändert)",
        "LANG": "de-AT" if STAAT == "AT" else "de",
        "GEB_TEXT": ("als Blöcke aus Grundriss und Laserscan-Höhe auf dem Luftbild. Einfärben nach Nutzung, Höhe oder Dachfarbe." if STAAT == "AT"
                     else "mit Dachformen auf dem aktuellen Luftbild. Einfärben nach Nutzung, Höhe oder Bodenrichtwert."),
        "STAND_TEXT": ("Gebäude und Adressen ändern sich seltener und werden mit den Stichtagsdaten des BEV nachgezogen." if STAAT == "AT"
                       else "Gebäude, Adressen und Bodenrichtwerte ändern sich seltener und werden nur bei neuen Veröffentlichungen der Landesvermessung nachgezogen."),
        "LAGE_TEXT": "Luftqualität und Müllabfuhr." if STAAT == "AT" else "Warnungen, Luft, Baustellen und Störungen.",
    }


def bedingt(s, feat, name):
    """Entfernt <!--IF x--> ... <!--ENDIF--> Bloecke, deren Baustein aus ist (verschachtelt)."""
    out, stack = [], []
    for tok in re.split(r"(<!--IF [a-z_]+-->|<!--ENDIF-->)", s):
        m = re.fullmatch(r"<!--IF ([a-z_]+)-->", tok)
        if m:
            if m.group(1) not in feat:
                sys.exit("Unbekannter Baustein %r in %s (Namen: %s)" % (m.group(1), name, ", ".join(sorted(feat))))
            stack.append(feat[m.group(1)])
        elif tok == "<!--ENDIF-->":
            if not stack:
                sys.exit("<!--ENDIF--> ohne <!--IF--> in " + name)
            stack.pop()
        elif all(stack):
            out.append(tok)
    if stack:
        sys.exit("<!--IF--> ohne <!--ENDIF--> in " + name)
    return "".join(out)


def ort_js():
    nb = ORT.get("nachbarort")
    fp = ORT["fahrplan"]
    v = ORT.get("veroeffentlichung", {})
    b = bausteine()
    f = features()
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
        "landwirt": f["bodenfeuchte"], "waldbrand": b["waldbrand"], "meldeportal": b["meldeportal"], "drohne": b["drohne"],
        "notfall": b["notfall"], "klima": b["klima"], "geschichte": b["geschichte"], "touren": b["touren"], "webcam": b["webcam"],
        "staat": STAAT, "zeitzone": ORT.get("zeitzone") or ("Europe/Vienna" if STAAT == "AT" else "Europe/Berlin"),
        "hoehe": "m ü. A." if STAAT == "AT" else "m über NHN", "brw": b["brw"], "verordnungen": b["verordnungen"], "gewaesser": b["gewaesser"],
        "landName": ORT["land"]["name"], "gkz": ORT["geo"]["gemeindeschluessel"],
        "wetterStation": ORT["geo"].get("wetter_station"), "wetterStationName": ORT["geo"].get("wetter_station_name"),
    }
    return "window.ORT = " + json.dumps(o, ensure_ascii=False) + ";\n"


def main():
    w = werte()
    feat = features()
    vor = os.path.join(ROOT, "vorlage")
    site = os.path.join(ROOT, "site")
    for name in SEITEN:
        quelle = os.path.join(vor, name)
        ziel = os.path.join(site, name)
        if name == "touren.html" and not feat["touren"]:
            if os.path.exists(ziel):
                os.remove(ziel)  # Baustein aus: keine Seite
            continue
        s = open(quelle, encoding="utf-8").read().replace("\r\n", "\n")
        s = bedingt(s, feat, name)

        def ersetze(m):
            k = m.group(1)
            if k not in w:
                sys.exit("Unbekannter Platzhalter {{%s}} in %s" % (k, name))
            return w[k] if k.endswith("_HTML") else html.escape(w[k], quote=True)
        s = re.sub(r"\{\{([A-Z_]+)\}\}", ersetze, s)
        rest = re.findall(r"\{\{[A-Z_]+\}\}", s)
        if rest:
            sys.exit("Unersetzte Platzhalter in %s: %s" % (name, rest))
        s = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", s)  # Leerzeilen, die entfernte Bloecke hinterlassen
        open(ziel, "w", encoding="utf-8", newline="\n").write(s)
        print("geschrieben:", name)
    os.makedirs(os.path.join(site, "data"), exist_ok=True)
    open(os.path.join(site, "data", "ort.js"), "w", encoding="utf-8", newline="\n").write(ort_js())
    print("geschrieben: data/ort.js")
    ev = os.path.join(site, "data", "events_auto.js")  # Platzhalter, solange kein Termin-Abruf eingerichtet ist
    if not os.path.exists(ev):
        open(ev, "w", encoding="utf-8", newline="\n").write('window.AL_EVENTS_AUTO={"stand":null,"quellen":[],"items":[]};\n')
        print("geschrieben: data/events_auto.js (leer)")
    for datei in optionale_dateien():  # Daten der Bausteine: leerer Platzhalter, bis das Abrufskript sie erzeugt hat
        name = os.path.basename(datei)
        if datei.startswith("data/") and name in PLATZHALTER and not os.path.exists(os.path.join(site, datei)):
            open(os.path.join(site, datei), "w", encoding="utf-8", newline="\n").write("window.%s=null;\n" % PLATZHALTER[name])
            print("geschrieben: %s (leerer Platzhalter, Abrufskript noch nicht gelaufen)" % datei)
    leeren(site, feat)


def leeren(site, feat):
    """Datendateien abgeschalteter Bausteine auf den leeren Platzhalter setzen. Die Seiten laden manche davon immer
    (z. B. brw.js, verordnungen.js, gewaesser.js); stuende dort noch der Stand eines frueheren Laufs, zeigte die Karte ihn weiter an."""
    for name, f in DATEN_BAUSTEIN.items():
        if feat.get(f):
            continue
        p = os.path.join(site, "data", name)
        leer = "window.%s=null;\n" % PLATZHALTER[name]
        alt = open(p, encoding="utf-8").read() if os.path.exists(p) else None
        if alt != leer and (alt is not None or name in IMMER_GELADEN):
            open(p, "w", encoding="utf-8", newline="\n").write(leer)
            print("geschrieben: data/%s (Baustein aus%s)" % (name, ", alter Stand entfernt" if alt else ""))


IMMER_GELADEN = ("brw.js", "verordnungen.js", "gewaesser.js")  # karte.html laedt sie ohne Bedingung: Platzhalter auch ohne frueheren Lauf


if __name__ == "__main__":
    main()
