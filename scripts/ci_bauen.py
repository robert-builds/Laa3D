"""Bauen fuer GitHub Pages (.github/workflows/pages.yml): entscheidet zwischen Erstaufbau und Wochenlauf.

Die Rohdaten, der Zustand und die erzeugten Seitendaten werden zwischen den Laeufen im Cache von GitHub Actions gehalten.
- Kein Stand im Cache, Stand aelter als GEO_TAGE oder Umgebungsvariable VOLLSTAENDIG=1: Erstaufbau (Gebaeude, Adressen,
  Luftbild, Gelaende neu; fuer Laa rund 40 Minuten). Bricht ein Erstaufbau ab, setzt der naechste Lauf mit den schon
  geladenen Dateien fort (fetch.py laedt nur, was fehlt).
- Sonst: Wochenlauf (OSM, Fahrplan, Verordnungen, Seiten; wenige Minuten).
Selten benoetigte Daten (Ortsgeschichte) holt das Skript, wenn sie fehlen.

Aufruf: python scripts/ci_bauen.py
"""
import datetime as dt, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from geo import ORT  # noqa: E402

STEMPEL = os.path.join(ROOT, "data", "raw", "ci_geodaten.txt")
GEO_TAGE = 92  # Gebaeude, Adressen und Luftbild werden vierteljaehrlich erneuert
sys.stdout.reconfigure(encoding="utf-8")


def run(*args, must=True):
    print("\n>>>", " ".join(args), flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, args[0])] + list(args[1:]), cwd=ROOT)
    if r.returncode and must:
        sys.exit("Schritt fehlgeschlagen: %s (Code %d)" % (args[0], r.returncode))
    return r.returncode


def alter_tage():
    try:
        d = dt.date.fromisoformat(open(STEMPEL, encoding="utf-8").read().strip())
        return (dt.date.today() - d).days
    except (OSError, ValueError):
        return None


def geodaten_leeren():
    """Vor einem Erstaufbau: alte Gebaeude, Adressen, Kacheln und Luftbilder weg, damit fetch.py sie neu holt."""
    raw = os.path.join(ROOT, "data", "raw", "gemeinde")
    for p in ("at", "lod2", "addr", "osm", "boundary.json", "ortsteile_geom.json", "cells.json", "street_names.json"):
        q = os.path.join(raw, p)
        if os.path.isdir(q):
            shutil.rmtree(q)
        elif os.path.exists(q):
            os.remove(q)
    for p in (os.path.join(ROOT, "data", "raw", "at", "adressregister.zip"), os.path.join(ROOT, "data", "raw", "dgm")):
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.exists(p):
            os.remove(p)
    img = os.path.join(ROOT, "site", "img")
    for f in os.listdir(img) if os.path.isdir(img) else []:
        if f.endswith((".jpg", ".png")) and f != "vorschau.jpg":
            os.remove(os.path.join(img, f))


def main():
    alter = alter_tage()
    zellen = os.path.exists(os.path.join(ROOT, "data", "raw", "gemeinde", "cells.json"))
    voll = os.environ.get("VOLLSTAENDIG") == "1" or not zellen or alter is None or alter > GEO_TAGE
    print("Stand der Geodaten: %s, Lauf: %s" % ("keiner" if alter is None else "%d Tage alt" % alter, "Erstaufbau" if voll else "Wochenlauf"))
    if voll:
        if os.environ.get("VOLLSTAENDIG") == "1" or (alter is not None and alter > GEO_TAGE):
            geodaten_leeren()  # Erneuerung; ohne Stempel (erster oder abgebrochener Lauf) bleibt Vorhandenes und wird fortgesetzt
        run("erstaufbau.py")
        os.makedirs(os.path.dirname(STEMPEL), exist_ok=True)
        open(STEMPEL, "w", encoding="utf-8").write(dt.date.today().isoformat())
    else:
        run("update_weekly.py")
    gesch = os.path.join(ROOT, "site", "data", "ortsgeschichte.js")
    if (ORT.get("bausteine") or {}).get("ortsgeschichte") and (not os.path.exists(gesch) or os.path.getsize(gesch) < 40):
        run("fetch_ortsgeschichte.py", must=False)
        run("versionieren.py")
    if run("pruefe_veroeffentlichung.py", must=False):
        sys.exit("Pruefung nicht bestanden: Seite wird nicht veroeffentlicht")


if __name__ == "__main__":
    main()
