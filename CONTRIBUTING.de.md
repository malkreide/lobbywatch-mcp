# Mitwirken bei lobbywatch-mcp

[🇬🇧 English version](CONTRIBUTING.md)

Danke für das Interesse an `lobbywatch-mcp`. Das Projekt ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide). Beiträge jeder Grössenordnung — Bug-Reports, Dokumentation, neue Tools, Performance — sind willkommen.

## Entwicklungs-Setup

```bash
git clone https://github.com/malkreide/lobbywatch-mcp.git
cd lobbywatch-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests ausführen

Nur offline (schnell, entspricht CI):

```bash
pytest -m "not live"
```

Inklusive Live-Probes gegen API und Dump:

```bash
pytest -m live
```

## Linting

```bash
ruff check .
ruff format .
```

## Design-Prinzipien

1. **No-Auth-First.** Alle Phase-1-Tools müssen ohne Credentials funktionieren.
2. **Live-Validierung vor dem Coden.** Wer ein Tool gegen einen Upstream-Endpoint baut, probiert den Endpoint zuerst live aus und dokumentiert die Erkenntnisse im PR.
3. **Namensnennung ist nicht verhandelbar.** Jede Antwort läuft durch ein Pydantic-Envelope mit der CC-BY-SA-4.0-Attribution. Nicht umgehen.
4. **Portfolio-Synergie.** Wenn ein Feature besser in einen anderen Server passt (`parlament-mcp`, `register-mcp`, …), besser dort einbringen als diesen Server aufblähen.

## Pull Requests

Conventional Commits verwenden (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) und `CHANGELOG.md` unter `[Unreleased]` nachführen.

## Die Live-Suite: wann sie läuft, und wer ein rotes Ergebnis sieht

**Kadenz:** jeden Montag um 04:33 UTC, dazu jederzeit von Hand über *Actions → Live-Tests → Run
workflow*. Siehe [`.github/workflows/live-tests.yml`](.github/workflows/live-tests.yml).

**Wer es sieht:** Ein roter Lauf öffnet ein Issue mit dem Label `upstream` und dem stabilen Titel «Live-Tests gegen cms.lobbywatch.ch rot (<Datum>)». Ein zweiter roter Lauf erkennt das offene Issue am Titelanfang und hängt sich an denselben Thread, statt ein zweites aufzumachen. Wird die Suite wieder grün, schliesst sich das Issue selbst.

**Drei Antworten, nicht zwei.** `scripts/classify_live_run.py` liest das JUnit-XML statt des
Exit-Codes und unterscheidet: `clear` (gelaufen, grün), `finding` (gelaufen,
etwas gefallen) und `unknown` (nicht gelaufen — Installation gescheitert, null
Tests eingesammelt, alle übersprungen). Ein `unknown` schliesst nie ein Issue:
Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der Quelle hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — so stirbt dieser Check, und er ist der einzige im Repo, der
einer falschen Grundannahme über cms.lobbywatch.ch widersprechen kann. Jeder andere Test
prüft gegen eine Fixture, und die Fixture ist aus derselben Annahme geschrieben
wie der Code.
