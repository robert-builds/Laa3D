# Österreich (Beispiel: Laa an der Thaya)

Mit `"staat": "AT"` unter `land` in `ort.json` nutzt die Vorlage österreichische Dienste statt der Brandenburger. Alles andere (OpenStreetMap, Fahrplan, Seite, Wochenlauf) bleibt gleich.

## Datenquellen

| Baustein | Quelle | Lizenz | Abruf |
|---|---|---|---|
| Gebäude | BEV, Digitales Landschaftsmodell – Bauwerke (Grundriss, Boden- und Objekthöhen aus dem Laserscan) | CC BY 4.0 | `scripts/fetch_at.py lod2`, GeoPackage österreichweit (rund 2,6 GB); mit `pyogrio` wird nur der Ausschnitt über das Netz gelesen (für Laa rund 20 Minuten, 11.706 Bauwerke im Rechteck, 5.852 in der Gemeinde) |
| Adressen, Nutzung der Gebäude | BEV, Österreichisches Adressregister, Stichtagsdaten (Relationale Tabellen) | Nutzungsbedingungen des BEV: Hinweis „© Österreichisches Adressregister, Stichtagsdaten vom …“ | `scripts/fetch_at.py addr`, ZIP rund 120 MB |
| Luftbild | basemap.at, Orthofoto (WMTS) | CC BY 4.0, „Datenquelle: basemap.at“ | `scripts/fetch_at.py dop`, Kacheln werden in `data/raw/at/basemap` zwischengespeichert |
| Gelände, Relief | BEV, ALS-Höhenraster (Geländemodell, 1 m, 50-km-Kacheln) | CC BY 4.0 | `scripts/fetch_dgm.py`, liest die Übersichtsstufe 8 m über das Netz (braucht `rasterio`, `numpy`) |
| Fahrplan | ÖBB-Personenverkehr AG, Soll-Fahrplan GTFS | CC BY 4.0 | im Wochenlauf; `{jahr}` in `fahrplan.gtfs_url` wird durch das neueste vorhandene Fahrplanjahr ersetzt |
| Verordnungen | data.gv.at (Bezirkshauptmannschaft, Gemeinde) | CC BY 4.0 je Datensatz | `scripts/fetch_verordnungen.py`, im Wochenlauf |
| Gewässer-Messstellen | Hydrographischer Dienst Niederösterreich (nur Name und Lage) | Verweis auf die Seite des Landes, keine Messwerte | `scripts/fetch_gewaesser.py`, im Wochenlauf |
| Straßen, Orte, Grenzen, Katastralgemeinden | OpenStreetMap | ODbL | wie überall |

Live im Browser (nur nach Klick „Live-Daten laden“):

| Thema | Dienst | Lizenz / Hinweis |
|---|---|---|
| Messwerte der Wetterstation | `dataset.api.hub.geosphere.at` (GeoSphere Austria, TAWES, 10 Minuten) | CC BY 4.0; Station in `geo.wetter_station` |
| Amtliche Wetterwarnungen | `warnungen.zamg.at` (GeoSphere Austria) | Warnungen für die Gemeinde, drei Stufen |
| Vorhersage, Bewölkung | `api.open-meteo.com` | CC BY 4.0; Modellwerte |
| Luftqualität | `air-quality-api.open-meteo.com` | CC BY 4.0; Modell (CAMS), keine Messung |
| Bahn live | `v6.oebb.transport.rest` (inoffiziell, HAFAS der ÖBB) | ohne Zusage; Haltestellen werden über den Namen gesucht |
| Müllabfuhr | eingebettete Seite des Abfallverbands (Laa: GAUL) | Seite setzt Cookies, eigener Schalter |

Bausteine der Vorlage, die in Österreich laufen: `notfall` (OSM), `touren` (OSM), `ortsgeschichte` (Wikipedia), Hangneigung und Senken (aus dem Gelände), `drohnenhinweis` (verweist in Österreich auf Dronespace der Austro Control). Nur für Deutschland und daher für Laa aus: `landwirtschaft`, `klima`, `webcam` (DWD), `waldbrand`, `baustellen`, `bodenrichtwerte` (Brandenburg). `ort_pruefen.py` meldet einen Fehler, wenn einer davon eingeschaltet ist.

## Was es in Österreich nicht gibt oder anders ist

- **Dachformen (LoD2):** Das DLM liefert Grundrisse mit Höhen, keine Dächer. Die Gebäude stehen als Blöcke (LoD1) in der Höhe des Medians der Laserscan-Punkte; die Gesamthöhe ist der höchste Punkt. Darum ist die Solar-Schätzung ausgeschaltet (`solar_kwh_je_kwp: null`).
- **Bodenrichtwerte:** kein offener amtlicher Datenbestand, Baustein entfällt.
- **Baustellen:** kein offener Dienst für Landesstraßen in Niederösterreich mit Browser-Zugriff gefunden. Stattdessen zeigt die Karte die Verkehrsverordnungen der Bezirkshauptmannschaft (darunter vorübergehende Sperren).
- **Höhen:** Meter über Adria (m ü. A.), nicht über NHN.
- **Busse:** Der offene ÖBB-Feed enthält nur die Bahn. Busse (VOR, Postbus) stehen im Feed der Mobilitätsverbünde Österreich (data.mobilitaetsverbuende.at). Dafür braucht es eine kostenlose Registrierung und die Annahme der Lizenz auf der Plattform. Dann in `ort.json` unter `fahrplan.mvo_feed` die Download-Adresse des Datensatzes eintragen und die Zugangsdaten **nur** als Umgebungsvariablen `MVO_USER` und `MVO_PASSWORD` setzen (nie in `ort.json` oder Git). Der Wochenlauf holt dann diesen Feed statt des ÖBB-Feeds. Die Plattform hat eine Umstellung ihrer Schnittstelle angekündigt; die Anmeldung über `user.mobilitaetsverbuende.at` ist nicht getestet.
- **Haltestellen live:** Die Kennungen im ÖBB-Feed sind keine HAFAS-Kennungen. Die Karte sucht die Haltestelle deshalb im Echtzeitdienst über den Namen (nächster Treffer innerhalb von 500 m).

## Einrichten

```
pip install -r requirements.txt
python scripts/ort_pruefen.py
python scripts/erstaufbau.py
```

`fetch_at.py` und `fetch_dgm.py` rechnen die Koordinaten selbst um (MGI/Gauß-Krüger und ETRS89-LAEA in `scripts/geo.py`, geprüft gegen PROJ). `pyproj` ist nicht nötig.

Für einen anderen Ort in Österreich in `ort.json` ändern: `name`, `geo.*` (OSM-Relation der Gemeinde, Gemeindekennziffer, Mittelpunkt, Umgrenzung, Wetterstation), `bausteine.verordnungen.behoerden` (zuständige Bezirkshauptmannschaft und Gemeinde), `bausteine.muellabfuhr`. Die Wetterstationen stehen unter `https://dataset.api.hub.geosphere.at/v1/station/current/tawes-v1-10min/metadata`. Die Gewässer-Messstellen gibt es so nur für Niederösterreich; in anderen Ländern `bausteine.gewaesser` auf `null` setzen.
