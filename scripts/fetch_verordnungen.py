"""Verordnungen fuer die Gemeinde aus dem Open-Data-Katalog data.gv.at (Oesterreich, CC BY 4.0).

Die Bezirkshauptmannschaften in Niederoesterreich veroeffentlichen ihre Verkehrsverordnungen (dauernde und vorübergehende,
etwa Sperren fuer Maerkte, Baustellen, Geschwindigkeitsbeschraenkungen) als einzelne Datensaetze auf data.gv.at, ebenso viele
Gemeinden ihre Verordnungen. Dieses Skript sucht sie ueber die Such-Schnittstelle des Katalogs, behaelt nur die der Behoerden aus
ort.json (bausteine.verordnungen.behoerden), die die Gemeinde oder eine ihrer Ortschaften nennen, und legt Titel, Kurztext,
Datum und den Verweis auf das amtliche Dokument ab. Den Inhalt der Dokumente liest es nicht.
Nennt der Text eine Strasse der Gemeinde (Adressregister), bekommt die Verordnung einen Punkt auf der Karte (Mitte der Adressen).

Aufruf : python scripts/fetch_verordnungen.py     (laeuft im Wochenlauf, wenn ort.json bausteine.verordnungen gesetzt ist)
Ausgabe: site/data/verordnungen.js   window.AL_VO = {stand, quelle, items: [...]}
"""
import datetime as dt, json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from geo import ORT  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "site", "data", "verordnungen.js")
API = "https://www.data.gv.at/api/hub/search/search?"
UA = ORT.get("kontakt_ua") or "MyCity3D"
sys.stdout.reconfigure(encoding="utf-8")


def txt(v):
    if isinstance(v, dict):
        return v.get("de") or next(iter(v.values()), "") or ""
    return v or ""


def suche(q, page):
    u = API + urllib.parse.urlencode({"q": q, "limit": 100, "page": page, "sort": "modified+desc"})
    for t in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60) as r:
                return json.load(r)["result"]["results"]
        except Exception as e:  # Katalog kurz nicht erreichbar
            last = e
            time.sleep(5 * (t + 1))
    raise RuntimeError("data.gv.at nicht erreichbar: %s" % last)


def load_js(path, var):
    s = open(path, encoding="utf-8").read()
    return json.loads(re.search(re.escape(var) + r"=(.*);\s*$", s, re.S).group(1))


def main():
    cfg = (ORT.get("bausteine") or {}).get("verordnungen")
    if not cfg:
        print("bausteine.verordnungen ist nicht gesetzt: nichts zu tun")
        return
    behoerden = [b.lower() for b in cfg.get("behoerden") or []]
    name = cfg.get("suchbegriff") or ORT["name"]
    monate = int(cfg.get("monate") or 18)
    grenze = (dt.date.today() - dt.timedelta(days=31 * monate)).isoformat()
    meta = load_js(os.path.join(ROOT, "site", "data", "meta.js"), "window.AL_TILES={};window.AL_META")
    orte = [name] + [o["n"] for o in meta["ortsteile"] if o["n"] != name]
    addr = load_js(os.path.join(ROOT, "site", "data", "addr.js"), "window.AL_ADDR")
    lage = {}  # Strasse -> Mitte ihrer Adresspunkte
    for r in addr["rows"]:
        lage.setdefault(r[0], []).append((r[2], r[3]))
    strassen = sorted(((s, i) for i, s in enumerate(addr["streets"]) if len(s) > 4 and i in lage), key=lambda t: -len(t[0]))

    gesehen, items = set(), []
    for q in ['"%s" Verordnung' % name] + ['"%s"' % o for o in orte]:
        for page in range(5):
            res = suche(q, page)
            for r in res:
                rid = r.get("id")
                if rid in gesehen:
                    continue
                pub = r.get("publisher") or r.get("creator") or {}
                pub = (pub.get("name") if isinstance(pub, dict) else str(pub)) or ""
                if not any(b in pub.lower() for b in behoerden):
                    continue
                titel, text = txt(r.get("title")), txt(r.get("description"))
                if "verordnung" not in (titel + " " + text).lower():
                    continue
                gemeindeamt = name.lower() in pub.lower()  # Verordnungen der Gemeinde selbst
                if not gemeindeamt and not any(re.search(r"\b%s\b" % re.escape(o), text) for o in orte):
                    continue
                datum = (r.get("issued") or (r.get("catalog_record") or {}).get("issued") or r.get("modified") or "")[:10]
                if datum and datum < grenze:
                    continue
                gesehen.add(rid)
                docs = [u for d in r.get("distributions") or [] for u in (d.get("access_url") or []) if u.startswith("https://")]
                art = "vorübergehend" if titel.startswith("Vorübergehende") else "dauernd" if titel.startswith("Dauernde") else "gemeinde" if gemeindeamt else "sonst"
                it = {"id": rid, "titel": titel, "text": text.strip()[:400], "art": art, "datum": datum, "behoerde": pub.split(",")[0],
                      "doc": docs[0] if docs else None, "seite": r.get("resource")}
                for s, i in strassen:  # erste genannte Strasse der Gemeinde: Punkt auf der Karte
                    if re.search(r"(?<![\wäöüß])%s(?![\wäöüß])" % re.escape(s), text):
                        pts = lage[i]
                        it.update({"s": s, "x": round(sum(p[0] for p in pts) / len(pts), 1), "z": round(sum(p[1] for p in pts) / len(pts), 1)})
                        break
                items.append(it)
            if len(res) < 100:
                break
            time.sleep(1)
    items.sort(key=lambda i: i["datum"] or "", reverse=True)
    out = {"stand": dt.date.today().isoformat(), "monate": monate, "quelle": "https://www.data.gv.at", "lizenz": "CC BY 4.0", "items": items}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.AL_VO=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("Verordnungen: %d (letzte %d Monate), davon mit Ort auf der Karte: %d" % (len(items), monate, sum(1 for i in items if "x" in i)))
    for i in items[:12]:
        print("  %s  %-14s %s | %s" % (i["datum"], i["art"], i["titel"][:60], i.get("s") or ""))


if __name__ == "__main__":
    main()
