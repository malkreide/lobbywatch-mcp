#!/usr/bin/env bash
#
# SessionStart-Hook: meldet, wie viele Commits der ausgecheckte Stand hinter
# origin/<default-branch> liegt. Bei 0 schweigt er.
#
# WARUM (ausführlich in .claude/hooks/README.md):
# Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
# Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
# die das Gate einführten, an dem der Branch scheiterte. Die Prüfung kostet
# eine Sekunde und ersetzt eine Fehlersuche in den falschen Dateien.
#
# GRUNDREGEL: Dieser Hook blockiert die Session NIEMALS.
# Kein Netz, kein Remote, detached HEAD, flatterndes DNS, kein git — jeder
# dieser Fälle endet still in `exit 0`. Ein Hook, der bei Netzproblemen die
# Arbeit anhält, wird nach dem zweiten Mal abgeschaltet und schützt danach
# gar nichts. Deshalb hier bewusst KEIN `set -e` und KEIN `pipefail`: ein
# nicht-null Exit einer Teilprüfung ist der Normalfall, nicht der Abbruch.

set -u

# Sekunden für jeden einzelnen Netzaufruf (ls-remote, fetch).
FETCH_TIMEOUT="${CLAUDE_STALENESS_FETCH_TIMEOUT:-5}"

# Keine interaktiven Prompts. Ein Credential- oder Host-Key-Dialog hätte
# keinen Menschen zum Antworten und würde bis zum Timeout stehen.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=/bin/echo
export SSH_ASKPASS=/bin/echo
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -oBatchMode=yes -oStrictHostKeyChecking=accept-new -oConnectTimeout=5}"
export GCM_INTERACTIVE=never

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

command -v git >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# `timeout` fehlt auf manchen Systemen (macOS ohne coreutils). Der Fallback
# begrenzt selbst, damit der Sessionstart auch dort nicht hängen kann.
if command -v timeout >/dev/null 2>&1; then
    run_limited() { timeout "$FETCH_TIMEOUT" "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
    run_limited() { gtimeout "$FETCH_TIMEOUT" "$@"; }
else
    run_limited() {
        "$@" &
        _pid=$!
        _waited=0
        while kill -0 "$_pid" 2>/dev/null; do
            if [ "$_waited" -ge "$FETCH_TIMEOUT" ]; then
                kill -9 "$_pid" 2>/dev/null
                wait "$_pid" 2>/dev/null
                return 124
            fi
            sleep 1
            _waited=$((_waited + 1))
        done
        wait "$_pid"
    }
fi

git remote get-url origin >/dev/null 2>&1 || exit 0

# Default-Branch ERMITTELN, nicht raten. Mindestens ein Repo im Portfolio
# nutzt `master`; die Annahme `main` hat dort schon einen Branch 15 Commits
# alt werden lassen, weil der fetch mit «couldn't find remote ref main»
# scheiterte und niemand hinsah.
default_branch=""

# 1. Lokal gespeichertes origin/HEAD — kostet kein Netz.
symref=$(git symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
[ -n "$symref" ] && default_branch="${symref#refs/remotes/origin/}"

# 2. Sonst den Remote fragen, begrenzt.
if [ -z "$default_branch" ]; then
    ls_out=$(run_limited git ls-remote --symref origin HEAD 2>/dev/null) || ls_out=""
    default_branch=$(
        printf '%s\n' "$ls_out" |
            sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]].*|\1|p' |
            head -1
    )
fi

# Kein Default-Branch ermittelbar -> schweigen. Hier NICHT auf `main`
# zurückfallen: eine erfundene Referenz erzeugt entweder einen Fehler oder,
# schlimmer, eine falsche Zahl.
[ -n "$default_branch" ] || exit 0

# Ohne erfolgreichen fetch gibt es keine belastbare Zahl. Der veraltete
# origin/<branch> im Klon wäre genau die Lüge, gegen die dieser Hook antritt.
run_limited git fetch --quiet origin "$default_branch" >/dev/null 2>&1 || exit 0

# Unborn HEAD (frisches Repo ohne Commit) hat nichts zu vergleichen.
git rev-parse --verify --quiet HEAD >/dev/null 2>&1 || exit 0

behind=$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null) || exit 0
case "$behind" in
    '' | *[!0-9]*) exit 0 ;;
esac

# Ausgabe nur, wenn tatsächlich Commits fehlen.
[ "$behind" -gt 0 ] || exit 0

# detached HEAD ist kein Fehlerfall, nur eine andere Beschriftung.
head_label=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -z "$head_label" ] || [ "$head_label" = "HEAD" ]; then
    head_label="detached HEAD $(git rev-parse --short HEAD 2>/dev/null)"
fi

if [ "$behind" -eq 1 ]; then
    commits="1 Commit"
else
    commits="$behind Commits"
fi

printf 'Klon-Aktualitaet: %s liegt %s hinter origin/%s zurueck.\n' \
    "$head_label" "$commits" "$default_branch"
printf 'Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht:\n'
printf 'es fehlen moeglicherweise genau die Commits, die ein CI-Gate einfuehren.\n'
printf 'Vor der Arbeit einordnen: git log --oneline HEAD..origin/%s\n' "$default_branch"

exit 0
