# SessionStart-Hook: Klon-Aktualität

`session-start.sh` meldet beim Sessionstart, wie viele Commits der
ausgecheckte Stand hinter `origin/<default-branch>` liegt. Liegt er nicht
zurück, gibt er nichts aus.

## Warum

Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
die das Gate einführten, an dem der Branch scheiterte. Die Fehlersuche lief
deshalb beide Male in den falschen Dateien: der Diff war korrekt, gefehlt hat
der Kontext, gegen den er geprüft wurde.

Die Prüfung kostet eine Sekunde und ersetzt diese Fehlersuche.

Der Hook ist die maschinelle Fassung des Abschnitts «Vor der Arbeit» in
`CLAUDE.md`. Ein Befund in Prosa altert still — er wird nicht rot, wenn ihn
niemand ausführt.

## Was er garantiert

**Er blockiert die Session niemals.** Das ist die erste Anforderung, nicht die
letzte. Ein Hook, der bei Netzproblemen die Arbeit anhält, wird nach dem
zweiten Mal abgeschaltet und schützt danach gar nichts. Still durch gehen:

| Fall | Verhalten |
| --- | --- |
| kein `git` im `PATH` | still, `exit 0` |
| kein Git-Arbeitsverzeichnis | still, `exit 0` |
| kein Remote `origin` | still, `exit 0` |
| Netz weg, DNS flattert, Remote antwortet nicht | still nach dem Timeout |
| Default-Branch nicht ermittelbar | still, `exit 0` |
| `HEAD` ohne Commit (frisches Repo) | still, `exit 0` |
| detached HEAD | Prüfung läuft, Ausgabe nennt den Kurz-Hash |
| 0 Commits im Rückstand | still, `exit 0` |

Das Skript setzt deshalb bewusst **kein** `set -e` und **kein** `pipefail`:
ein Exit ungleich null aus einer Teilprüfung ist hier der Normalfall.

## Timeout

Jeder Netzaufruf (`ls-remote`, `fetch`) ist auf 5 Sekunden begrenzt, über
`timeout(1)` bzw. `gtimeout`. Fehlen beide (macOS ohne coreutils), begrenzt
das Skript selbst per Hintergrundprozess und Poll-Schleife — es gibt keinen
Pfad, auf dem ein hängender `fetch` den Sessionstart hält.

Überschreibbar für langsame Verbindungen:

```bash
export CLAUDE_STALENESS_FETCH_TIMEOUT=10
```

`.claude/settings.json` setzt zusätzlich `"timeout": 20` als äussere Schranke
des Harness.

Interaktive Prompts sind abgeschaltet (`GIT_TERMINAL_PROMPT=0`,
`ssh -oBatchMode=yes`). Ein Credential-Dialog beim Sessionstart hätte keinen
Menschen zum Antworten und stünde bis zum Timeout.

## Default-Branch: ermittelt, nicht angenommen

Drei Server im Portfolio (`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`)
heissen ihren Standard-Branch `master`. Ein fest verdrahtetes `main` scheitert
dort mit «couldn't find remote ref main» — wer das für ein Netzproblem hält,
arbeitet weiter auf genau dem veralteten Klon, den der Hook melden sollte.
Genau so wurde ein Branch 15 Commits alt.

Ermittelt wird in zwei Stufen:

1. `git symbolic-ref refs/remotes/origin/HEAD` — lokal, ohne Netz.
2. `git ls-remote --symref origin HEAD` — nur falls Stufe 1 leer ist, mit
   Timeout.

Bleibt beides leer, **schweigt der Hook**. Ein Rückfall auf `main` wäre hier
schlimmer als keine Ausgabe: er liefert entweder einen Fehler oder, schlimmer,
eine falsche Zahl.

Aus demselben Grund vergleicht der Hook nur gegen ein frisch geholtes
`FETCH_HEAD`. Scheitert der `fetch`, wird nicht ersatzweise der im Klon
liegende `origin/<branch>` herangezogen — der ist genau die veraltete
Referenz, gegen die dieser Hook antritt.

## Manuell testen

```bash
CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/session-start.sh; echo "exit=$?"
```

Gegenprobe — künstlich veralteter Stand muss eine Meldung erzeugen:

```bash
git stash -u                       # falls nötig
git checkout --detach HEAD~3
CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/session-start.sh
git checkout -                     # zurück
```

Gegenprobe ohne Netz — muss still und mit `exit=0` durchlaufen:

```bash
GIT_SSH_COMMAND=false \
  git -c 'url.http://127.0.0.1:1/.insteadOf=https://github.com/' \
  --version >/dev/null   # nur Illustration; im Zweifel Remote temporär umbiegen
```

## Reichweite

Der Hook läuft in lokalen und in Remote-Sessions (Claude Code on the web).
Er ist nicht auf `$CLAUDE_CODE_REMOTE` eingeschränkt, weil ein veralteter
Klon lokal genauso eine rote CI erzeugt wie in der Cloud.

Wirksam wird er für alle künftigen Sessions erst, wenn er im Default-Branch
liegt.
