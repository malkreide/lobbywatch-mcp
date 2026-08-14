# CLAUDE.md

## Teil 1 — Portfolio-Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen: `git fetch origin main && git rev-list --count HEAD..origin/main`
Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess «nicht gefunden» nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

## Teil 2 — Dieses Repo

### ruff

Gepinnt auf `ruff==0.16.1`, einzige Fundstelle: `pyproject.toml`,
`[project.optional-dependencies].dev`. Die CI installiert daraus
(`pip install -e ".[dev]"`), sie nennt keine eigene Version.

**Befund:** `.pre-commit-config.yaml` existiert nicht. Damit gibt es keine
zweite Deklaration, die abweichen könnte — aber auch kein Gate vor dem Push.

### Gate-Befehle (wörtlich aus `.github/workflows/ci.yml`)

```bash
ruff check .
ruff format --check .

# Format-Stabilität der portfolioweit kopierten Skripte
for ll in 88 100 110 120; do
  ruff format --check --line-length "$ll" scripts/check_version_sync.py
done

pytest -m "not live" -q
python scripts/check_version_sync.py
```

Matrix: Python 3.11 / 3.12 / 3.13.

### Live-Tests

**Befund (DRIFT-005):** `tests/test_live.py` ist per `pytest -m "not live"`
aus der CI ausgeschlossen, und es gibt keinen geplanten Lauf — die einzigen
Workflows sind `ci.yml` (push/pull_request) und `publish.yml`, beide ohne
`schedule`/`cron`. Die Live-Suite läuft also nur, wenn jemand sie von Hand
startet. Ausgeschlossene Tests, die niemand ausführt, verrotten.
