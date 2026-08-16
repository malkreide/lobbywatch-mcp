"""Jeder externe Endpunkt, gefahren aus einer aufgezeichneten Antwort.

Die handgeschriebenen Stubs im Rest der Suite pruefen die *Fehler*-Pfade — ein
404, ein Timeout, ein kaputtes ZIP —, die sich nicht auf Zuruf aufzeichnen
lassen und als Erfindung in Ordnung sind. Was sie nicht koennen: die Form einer
Erfolgs-Antwort belegen. Sie stimmen mit dem ueberein, was ihr Autor annahm.

Der Dump ist der interessante Fall: 243 Parlamentarier zu je rund 380 kB, fast
alles davon verschachtelte Beziehungen. Die Aufzeichnung haelt alle
Skalarfelder und kuerzt nur die Listenlaenge — die Struktur der Eintraege samt
`organisation` und `verguetungen` bleibt.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`; neu aufzeichnen mit
`python scripts/record_fixtures.py`.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx
import pytest
import respx

from lobbywatch_mcp.client import LobbywatchClient
from lobbywatch_mcp.config import API_BASE, DUMP_URL
from tests.fixture_data import fixture_bytes, fixture_json, provenance, recorded_names

# Jeder externe Endpunkt dieses Servers und die Fixture dazu. Ein Endpunkt ohne
# Aufzeichnung faellt in `test_jeder_endpunkt_hat_eine_aufzeichnung`.
ENDPUNKTE = {
    "dump.zip": "dump.zip",
    "table/interessengruppe/aggregated/id/{id}": "interessengruppe.json",
    "search/default/{begriff}": "search.json",
}

GRUPPEN_ID = 1


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------


def test_provenance_nennt_ein_brauchbares_aufnahmedatum():
    """Eine Aufzeichnung ohne Datum ist eine undatierte Behauptung ueber die Quelle."""
    match = re.search(r"Aufgezeichnet am \*\*(\d{4}-\d{2}-\d{2})\*\*", provenance())
    assert match, "PROVENANCE.md nennt kein Aufnahmedatum im erwarteten Format"
    when = dt.date.fromisoformat(match.group(1))
    assert when <= dt.datetime.now(dt.UTC).date(), "Aufnahmedatum liegt in der Zukunft"


def test_jede_fixture_steht_in_der_provenance():
    """Sonst waechst der Ordner und der Nachweis bleibt zurueck."""
    text = provenance()
    fehlend = [n for n in recorded_names() if f"## `{n}`" not in text]
    assert not fehlend, f"ohne Eintrag in PROVENANCE.md: {fehlend}"


def test_jeder_endpunkt_hat_eine_aufzeichnung():
    """Bewacht die Regel selbst: eine aufgezeichnete Antwort je externem Endpunkt."""
    fehlend = sorted(set(ENDPUNKTE.values()) - set(recorded_names()))
    assert not fehlend, f"Endpunkte ohne Aufzeichnung: {fehlend}"


# --------------------------------------------------------------------------
# Der Dump
# --------------------------------------------------------------------------


@respx.mock
async def test_dump_aus_der_aufzeichnung(tmp_path):
    """Der Weg vom ZIP bis zu den abfragbaren Datensaetzen, ohne Netz."""
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=fixture_bytes("dump.zip")))
    client = LobbywatchClient(cache_dir=tmp_path)
    try:
        await client.ensure_dump_loaded()
        records = await client.all_parlamentarier()
    finally:
        await client.aclose()
    assert records, "die Aufzeichnung liefert Parlamentarier"
    assert all(r.get("anzeige_name") for r in records)
    assert all(r.get("id") for r in records)


@respx.mock
async def test_der_dump_haelt_die_verschachtelten_beziehungen(tmp_path):
    """Gekuerzt ist die Listenlaenge, nicht die Satzform.

    Die Beziehungen unter `interessenbindungen` tragen selbst wieder
    `organisation` und `verguetungen`. Eine erfundene Fixture haette diese
    Verschachtelung leicht flach geraten.
    """
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=fixture_bytes("dump.zip")))
    client = LobbywatchClient(cache_dir=tmp_path)
    try:
        await client.ensure_dump_loaded()
        records = await client.all_parlamentarier()
    finally:
        await client.aclose()

    mit_bindungen = [r for r in records if r.get("interessenbindungen")]
    assert mit_bindungen, "mindestens ein aufgezeichneter Parlamentarier traegt Bindungen"
    bindung = mit_bindungen[0]["interessenbindungen"][0]
    assert "organisation" in bindung, "die Bindung verschachtelt eine Organisation"
    assert isinstance(bindung["organisation"], dict)

    # Die Auswahlregel nimmt einen mit und einen ohne Zutrittsberechtigungen.
    # Nach Interessenbindungen zu waehlen traegt hier nicht: jeder der 243 hat
    # zwischen 4 und 114, und das Kuerzen macht daraus ueberall dieselbe Zahl.
    # Eine leere Liste bleibt dagegen leer — nur diese Achse ueberlebt.
    zutritte = sorted(len(r.get("zutrittsberechtigungen") or []) for r in records)
    assert zutritte[0] == 0, "ein Datensatz ohne Zutrittsberechtigungen gehoert dazu"
    assert zutritte[-1] > 0, "ein Datensatz mit Zutrittsberechtigungen gehoert dazu"


def test_der_dump_haelt_die_skalarfelder_vollstaendig():
    """113 Felder je Parlamentarier: gekuerzt wird die Liste, nicht der Satz."""
    import io
    import json
    import zipfile

    with zipfile.ZipFile(io.BytesIO(fixture_bytes("dump.zip"))) as zf:
        records = json.loads(zf.read(zf.namelist()[0]))
    skalare = [k for k, v in records[0].items() if not isinstance(v, list)]
    assert len(skalare) > 100, (
        f"nur {len(skalare)} Skalarfelder — die Aufzeichnung soll den ganzen Satz halten"
    )


# --------------------------------------------------------------------------
# Die Tabelle nach ID
# --------------------------------------------------------------------------


@respx.mock
async def test_interessengruppe_nach_id_aus_der_aufzeichnung(tmp_path):
    payload = fixture_json("interessengruppe.json")
    respx.get(f"{API_BASE}/table/interessengruppe/aggregated/id/{GRUPPEN_ID}").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = LobbywatchClient(cache_dir=tmp_path)
    try:
        gruppe = await client.fetch_lobbygruppe(GRUPPEN_ID)
    finally:
        await client.aclose()
    assert gruppe is not None, "eine bekannte ID darf nicht None liefern"
    assert gruppe.get("anzeige_name"), "die Gruppe traegt einen Anzeigenamen"
    assert "connections" in gruppe, "die Quelle verschachtelt Verbindungen unter `connections`"


# --------------------------------------------------------------------------
# Die Suche — und was sie zurzeit liefert
# --------------------------------------------------------------------------


def test_die_aufgezeichnete_suche_ist_leer_und_das_steht_im_nachweis():
    """Haelt einen Befund fest, den nur eine Aufzeichnung datieren kann.

    `search/default/{begriff}` antwortet mit HTTP 200 und `data: null` — fuer
    jeden geprueften Begriff. Der Pfad ist richtig; der Tabellen-Endpunkt
    antwortet normal. Wirkung: eine Abfrage nach *Namen* liefert zurzeit nichts,
    eine nach ID schon.

    Faellt dieser Test, weil die Suche wieder Treffer liefert, ist das eine gute
    Nachricht — dann gehoert die Aufzeichnung erneuert und der Befund aus
    PROVENANCE.md gestrichen.
    """
    suche = fixture_json("search.json")
    assert suche.get("success") is True, "die Quelle meldet Erfolg, nicht einen Fehler"
    assert not (suche.get("data") or []), (
        "die Suche liefert wieder Treffer — Aufzeichnung erneuern und den Befund "
        "in PROVENANCE.md streichen"
    )
    assert "die Suche liefert nichts" in provenance(), (
        "der Befund gehoert datiert in den Nachweis, nicht nur in diesen Test"
    )


@respx.mock
async def test_namenssuche_liefert_zurzeit_nichts(tmp_path):
    """Die Wirkung des Befunds, am echten Client statt an der Vermutung."""
    respx.get(url__startswith=f"{API_BASE}/search/default/").mock(
        return_value=httpx.Response(200, json=fixture_json("search.json"))
    )
    client = LobbywatchClient(cache_dir=tmp_path)
    try:
        treffer = await client.fetch_lobbygruppe("Bildung")
    finally:
        await client.aclose()
    assert treffer is None, (
        "solange die Quelle nichts liefert, ist None das ehrliche Ergebnis einer "
        "Namenssuche — kein Grund, etwas zu erfinden"
    )


@pytest.mark.parametrize("name", sorted(ENDPUNKTE.values()))
def test_jede_aufzeichnung_ist_nicht_leer(name):
    """Eine leere Datei sieht aus wie eine gueltige und prueft nichts."""
    assert fixture_bytes(name), f"{name} ist leer — neu aufzeichnen"


# --------------------------------------------------------------------------
# Der Nachweis, nachgerechnet
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(n for n in recorded_names() if n != "PROVENANCE.md"))
def test_die_pruefsumme_im_nachweis_stimmt(name):
    """Eine Pruefsumme, die niemand nachrechnet, ist Zierde.

    Sie steht im Nachweis, um genau einen Fall zu fangen: eine Aufzeichnung,
    die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort
    ist wieder eine erfundene — und von aussen ist ihr das nicht anzusehen.
    Ohne diesen Test faengt die Summe nichts.

    Gerechnet wird ueber die Bytes auf der Platte, nicht ueber den Loader:
    genau die hat der Recorder gehasht, und ein Loader, der unterwegs dekodiert
    oder normalisiert, wuerde die Pruefung gegen sich selbst fuehren.
    """
    import hashlib
    import re
    from pathlib import Path

    teile = provenance().split(f"## `{name}`", 1)
    assert len(teile) == 2, f"{name} hat keinen Block in PROVENANCE.md"
    treffer = re.search(r"\*\*SHA-256:\*\*\s*`([0-9a-f]{64})`", teile[1].split("## ", 1)[0])
    assert treffer, f"{name} steht ohne Pruefsumme im Nachweis"
    roh = (Path(__file__).resolve().parent / "fixtures" / name).read_bytes()
    assert hashlib.sha256(roh).hexdigest() == treffer.group(1), (
        f"{name} weicht vom Nachweis ab — von Hand nachgebessert? Neu aufzeichnen."
    )
