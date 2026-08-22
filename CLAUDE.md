# CLAUDE.md

## Teil 1 — Portfolio-Konventionen

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

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

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

Bis mindestens zum 22.8. um 08:30, also 23 Stunden später, blieb es dabei. In
der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden, ohne
dass jemand hineingesehen hat.

Drei Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann reagiert er mit 👍 und schreibt nichts.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein echter Review ist ein Review-Objekt («💡 Codex Review»,
mit Commit-Angabe), die Limit-Meldung ein gewöhnlicher Issue-Kommentar. Das
sind zwei verschiedene Abfragen — `get_reviews` gegen `get_comments`; wer nur
eine davon nimmt, übersieht die andere Hälfte. Genau so ist die Limit-Meldung
zuerst durchgerutscht.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Zeigt das freies Kontingent, während Reviews weiter
scheitern, ist das ein bekannter Fehler bei mehreren verbundenen Konten — dann
den GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — Dieses Repo

### ruff

Gepinnt auf `ruff==0.16.1`, einzige Fundstelle: `pyproject.toml`,
`[project.optional-dependencies].dev`. Die CI installiert daraus
(`pip install -e ".[dev]"`), sie nennt keine eigene Version.

**Befund:** `.pre-commit-config.yaml` existiert nicht. Damit gibt es keine
zweite Deklaration, die abweichen könnte — aber auch kein Gate vor dem Push.

Keine zweite Version in die Workflows schreiben: ein solcher Schritt liefe
nach dem dev-Install und überstimmte den Pin still.
`tests/test_werkzeug_versionen.py` fällt dann.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

### Gate-Befehle (wörtlich aus `.github/workflows/ci.yml`)

```bash
python scripts/check_ruff_pin.py
ruff check .
ruff format --check .

# Format-Stabilität der portfolioweit kopierten Skripte
for ll in 88 100 110 120; do
  ruff format --check --line-length "$ll" scripts/check_version_sync.py
done

pytest -m "not live" -q
python scripts/check_version_sync.py
```

Matrix: Python 3.11 / 3.12 / 3.13, **mit `fail-fast: false`** — im Portfolio
die Ausnahme. Eine rote 3.11 stoppt 3.12 und 3.13 hier also nicht, und das ist
beim Einordnen der Unterschied zwischen «versionsabhängig» und «überall
kaputt». Alle Gates laufen auf allen drei Feldern, keine `if:`-Ausnahme.

**Die ruff-Gates fahren `.`, nicht Pfade** — anders als in den meisten
Schwester-Servern, wo `src/ tests/ scripts/` steht. Der Umfang ist damit das
ganze Repo; nachgemessen sind es 66 Dateien im Format-Gate (19.08.2026, mit
`ruff==0.16.1`). Kein `include` unter `[tool.ruff]` setzen: Bei einem
`.`-Aufruf gibt es keine Pfadangabe im Befehl, die eine zu enge
Einschränkung noch sichtbar machen könnte — sie wirkt ungebremst und still.

Die Zahl ist ein Momentwert, kein Gate: sie wächst mit jeder neuen
Python-Datei und wird nicht rot, wenn sie veraltet. Vor dem Zitieren
nachmessen (`ruff format --check .`), nicht aus diesem Absatz abschreiben.

### Live-Tests

**DRIFT-005 ist erfüllt.** `.github/workflows/live-tests.yml` fährt
`tests/test_live.py` planmässig gegen `cms.lobbywatch.ch`: `cron: "33 4 * * 1"`
plus `workflow_dispatch`, ein roter Lauf öffnet bzw. schliesst ein
`upstream`-Issue. Die PR-CI schliesst dieselben Tests weiter per
`-m "not live"` aus — das ist hier korrekt, weil der geplante Lauf existiert.
`schedule` greift nur auf dem Default-Branch: Änderungen an der Datei wirken
erst nach dem Merge, vorher von Hand auslösen.

Hier stand das Gegenteil, und es war nach einem Tag falsch: Die CLAUDE.md
entstand am 14.08.2026, `live-tests.yml` kam am 15.08.2026 dazu (`c4d1b3f`).
Ein Befund in Prosa altert still — er wird nicht rot, wenn der Zustand sich
ändert, und wer ihm folgt, baut einen zweiten Workflow für etwas, das es
schon gibt.
