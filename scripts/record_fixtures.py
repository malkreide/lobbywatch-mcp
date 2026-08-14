#!/usr/bin/env python3
"""Zeichnet echte Lobbywatch-Antworten nach `tests/fixtures/` auf.

Warum: eine handgeschriebene Fixture kodiert die Annahme ihres Autors und kann
sie deshalb nicht widerlegen. In `i14y-mcp` blieb genau deshalb eine ganze Suite
gruen, waehrend drei Tools produktiv leere Titel lieferten — die Stubs hatten
einen Schluessel erfunden und stimmten dem Mapper zu statt der Quelle.

Drei Endpunkte, drei verschiedene Probleme:

* Der **Dump** ist ein ZIP mit einer 80-MB-JSON. Aufgezeichnet werden zwei von
  243 Parlamentariern; alle 113 Skalarfelder bleiben, die Beziehungslisten
  werden auf wenige Eintraege gekuerzt — deren Struktur samt `organisation` und
  `verguetungen` bleibt unangetastet. Fast die ganze Groesse steckt in
  `interessenbindungen`: 33 Eintraege zu je rund 10 kB.
* Die **Tabelle nach ID** antwortet normal und wird vollstaendig aufgezeichnet.
* Die **Suche** antwortet zurzeit auf jeden Begriff mit `count: 0` und
  `data: null` — siehe PROVENANCE.md. Aufgezeichnet wird, was sie liefert.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei schreibt dieses Skript nach
`tests/fixtures/PROVENANCE.md`. Neu aufzeichnen:

    python scripts/record_fixtures.py

Braucht Netzzugang zu `cms.lobbywatch.ch`. Entwicklungswerkzeug; weder das
Paket noch die Testsuite importieren es.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

API_BASE = "https://cms.lobbywatch.ch/de/data/interface/v1/json"
DUMP_URL = (
    "https://cms.lobbywatch.ch/sites/lobbywatch.ch/files/exports/"
    "lobbywatch_export_aggregated.json.zip"
)
DUMP_INNER = "aggregated_essential_parlamentarier_nested.json"
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# Zwei Parlamentarier, gewaehlt statt genommen — und zwar entlang der Achse, die
# das Kuerzen ueberlebt. Nach *Interessenbindungen* zu waehlen brachte nichts:
# jeder der 243 hat zwischen 4 und 114, und die Deckelung unten macht daraus
# ueberall dieselbe Zahl. `zutrittsberechtigungen` dagegen fehlen bei 34 ganz —
# eine leere Liste bleibt leer. Aufgezeichnet wird deshalb einer *mit* und einer
# *ohne* Zutrittsberechtigungen, ersterer zugleich der mit den meisten Bindungen.
PARLAMENTARIER = 2

# Beziehungslisten kuerzen, ihre Eintraege aber nicht: die Verschachtelung
# unter `organisation` und `verguetungen` ist genau die Satzform, die eine
# erfundene Fixture raten muesste.
NESTED_LIMIT = 3

# Fester Begriff und feste ID, nicht «irgendein»: eine vom Lauf abhaengige
# Auswahl erzeugte bei jedem Aufzeichnen einen anderen Diff.
SEARCH_TERM = "Bildung"
GRUPPEN_ID = 1


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "lobbywatch-mcp-recorder"})
    with urlopen(req, timeout=300) as resp:
        return resp.read()


def kuerze(eintrag: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Skalarfelder unveraendert, Beziehungslisten auf `NESTED_LIMIT` gekuerzt."""
    heraus: dict[str, Any] = {}
    zahlen: dict[str, int] = {}
    for schluessel, wert in eintrag.items():
        if isinstance(wert, list):
            zahlen[schluessel] = len(wert)
            heraus[schluessel] = wert[:NESTED_LIMIT]
        else:
            heraus[schluessel] = wert
    return heraus, zahlen


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict[str, Any]] = []
    print(f"Zeichne auf von {API_BASE} und dem Dump")

    def write(name: str, blob: bytes, url: str, rule: str) -> None:
        (FIXTURES / name).write_bytes(blob)
        entries.append(
            {
                "name": name,
                "url": url,
                "rule": rule,
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
        print(f"  ok  {name:<30} {len(blob):>8} B")

    def write_json(name: str, payload: Any, url: str, rule: str) -> None:
        write(
            name,
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            url,
            rule,
        )

    # --- Dump: ZIP mit grosser JSON --------------------------------------
    print(f"  lade {DUMP_URL} (rund 17 MB) ...")
    roh = fetch(DUMP_URL)
    with zipfile.ZipFile(io.BytesIO(roh)) as zf:
        alle = json.loads(zf.read(DUMP_INNER))
    mit_zutritt = [p for p in alle if p.get("zutrittsberechtigungen")]
    ohne_zutritt = [p for p in alle if not p.get("zutrittsberechtigungen")]
    if not mit_zutritt or not ohne_zutritt:
        print("!! keine zwei unterscheidbaren Formen gefunden — Auswahlregel pruefen")
        return 1
    dicht = max(mit_zutritt, key=lambda p: len(p.get("interessenbindungen") or []))
    duenn = ohne_zutritt[0]
    gewaehlt = [dicht, duenn][:PARLAMENTARIER]

    gekuerzt = []
    beschreibung = []
    for p in gewaehlt:
        klein, zahlen = kuerze(p)
        gekuerzt.append(klein)
        beschreibung.append(
            f"{p.get('anzeige_name')} ({len(p.get('interessenbindungen') or [])} Bindungen, "
            f"{len(p.get('zutrittsberechtigungen') or [])} Zutrittsberechtigungen)"
        )

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(DUMP_INNER, json.dumps(gekuerzt, ensure_ascii=False))
    write(
        "dump.zip",
        puffer.getvalue(),
        DUMP_URL,
        f"ZIP mit `{DUMP_INNER}`; {len(gekuerzt)} von {len(alle)} Parlamentariern, gewaehlt "
        f"einer mit und einer ohne Zutrittsberechtigungen ({'; '.join(beschreibung)}). "
        f"Alle Skalarfelder unveraendert, Beziehungslisten auf {NESTED_LIMIT} Eintraege "
        f"gekuerzt, deren Struktur unangetastet. Quelle: {len(roh)} B gepackt",
    )

    # --- Tabelle nach ID --------------------------------------------------
    url = f"{API_BASE}/table/interessengruppe/aggregated/id/{GRUPPEN_ID}"
    write_json(
        "interessengruppe.json",
        json.loads(fetch(url)),
        url,
        f"vollstaendig; Interessengruppe {GRUPPEN_ID}",
    )

    # --- Suche ------------------------------------------------------------
    url = f"{API_BASE}/search/default/{quote(SEARCH_TERM, safe='')}?{urlencode({'limit': 5})}"
    suche = json.loads(fetch(url))
    treffer = suche.get("data") or []
    write_json(
        "search.json",
        suche,
        url,
        f"vollstaendig; Suche nach {SEARCH_TERM!r} — die Quelle liefert "
        f"{len(treffer)} Treffer (siehe Hinweis oben)",
    )

    _write_provenance(recorded_at, entries, leere_suche=not treffer)
    print(f"\nPROVENANCE.md geschrieben, Aufzeichnungsdatum {recorded_at}")
    if not treffer:
        print("!! Die Suche lieferte keine Treffer — als Befund in PROVENANCE.md vermerkt.")
    return _warne_bei_ignorierten(entries)


def _warne_bei_ignorierten(entries: list[dict[str, Any]]) -> int:
    """Meldet Aufzeichnungen, die `.gitignore` ausschliesst.

    Eine ignorierte Fixture faellt lokal nicht auf — die Datei liegt ja da und
    die Suite ist gruen. Erst die CI klont ein Repo ohne sie und wird rot, mit
    einer Meldung, die nach einem Aufzeichnungsproblem aussieht statt nach einer
    Regel in `.gitignore`. Genau so ist es in `swiss-housing-mcp` passiert.
    """
    pfade = [str(FIXTURES / e["name"]) for e in entries]
    try:
        ergebnis = subprocess.run(
            ["git", "check-ignore", *pfade], capture_output=True, text=True, check=False
        )
    except OSError:
        return 0
    ignoriert = [z for z in ergebnis.stdout.splitlines() if z.strip()]
    if ignoriert:
        print("\n!! Diese Aufzeichnungen schliesst .gitignore aus, sie fehlen der CI:")
        for z in ignoriert:
            print(f"     {z}")
        print("   Ausnahme in .gitignore ergaenzen, z. B. `!tests/fixtures/*.zip`.")
        return 1
    return 0


def _write_provenance(recorded_at: str, entries: list[dict[str, Any]], leere_suche: bool) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}** von der Quelle dieses Servers:",
        f"`{API_BASE}` und dem woechentlichen Dump unter `cms.lobbywatch.ch`.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus.",
        "",
        "**Es sind Ausschnitte, keine Vollabzuege.** Die Auswahlregel steht je",
        "Datei dabei. Eine Fixture belegt die *Form* der Antwort und einen",
        "datierten Ausschnitt ihres Inhalts — nicht den Bestand. Aussagen ueber",
        "Vollstaendigkeit gehoeren in Live-Tests.",
        "",
        "**Der Dump ist gekuerzt, aber nicht beschnitten.** Die Quelle liefert ein",
        "ZIP mit einer 80-MB-JSON. Aufgezeichnet sind zwei von 243",
        "Parlamentariern: einer mit, einer ohne Zutrittsberechtigungen. Nach",
        "Interessenbindungen zu waehlen brachte nichts — jeder der 243 hat",
        "zwischen 4 und 114, und das Kuerzen macht daraus ueberall dieselbe Zahl;",
        "eine leere Liste bleibt dagegen leer. Alle 113 Skalarfelder bleiben",
        "unveraendert; die",
        "Beziehungslisten sind auf drei Eintraege gekuerzt, ihre Struktur samt",
        "`organisation` und `verguetungen` ist unangetastet. Fast die ganze",
        "Groesse steckt in `interessenbindungen` — 33 Eintraege zu je rund 10 kB.",
        "",
    ]
    if leere_suche:
        lines += [
            f"## Befund vom {recorded_at}: die Suche liefert nichts",
            "",
            "`search/default/{begriff}` antwortet mit HTTP 200, `success: true`,",
            "`count: 0` und `data: null` — fuer jeden geprueften Begriff",
            "(Bildung, Verkehr, Economiesuisse, Umwelt, Gewerkschaft). Der Pfad",
            "ist richtig: `search/simple/...` und `search/...` liefern 404, der",
            "Tabellen-Endpunkt nach ID antwortet normal mit knapp 60 kB.",
            "",
            "Wirkung: `fetch_lobbygruppe` schlaegt einen **Namen** ueber die Suche",
            "nach und liefert deshalb zurzeit fuer jeden Namen `None`. Abfragen",
            "ueber die numerische ID sind nicht betroffen. Das ist der Stand der",
            "Quelle an diesem Tag, kein Fehler dieses Servers — die Aufzeichnung",
            "haelt ihn datiert fest, statt ihn zu erfinden.",
            "",
        ]
    lines += [
        "Fehlerpfade — 404, Timeouts, kaputte ZIPs — bleiben handgeschrieben.",
        "Die lassen sich nicht auf Zuruf aufzeichnen.",
        "",
    ]
    for e in entries:
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url']}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            f"- **Groesse:** {e['bytes']} B",
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
