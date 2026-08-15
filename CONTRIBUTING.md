# Contributing to lobbywatch-mcp

[🇩🇪 Deutsche Version](CONTRIBUTING.de.md)

Thanks for your interest in improving `lobbywatch-mcp`. This project is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide). Contributions of any size — bug reports, documentation fixes, new tools, performance work — are welcome.

## Development setup

```bash
git clone https://github.com/malkreide/lobbywatch-mcp.git
cd lobbywatch-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

Offline only (fast, what CI runs):

```bash
pytest -m "not live"
```

Including live API + dump probes:

```bash
pytest -m live
```

## Linting

```bash
ruff check .
ruff format .
```

## Design principles

1. **No-Auth-First.** All Phase 1 tools must work without credentials.
2. **Live validation before coding.** If you add a tool that hits an upstream endpoint, verify the endpoint with a live probe first and document what you found in the PR.
3. **Attribution is non-negotiable.** Every response goes through a Pydantic envelope that carries the CC BY-SA 4.0 credit. Don't route around it.
4. **Portfolio synergy.** If a feature fits better in another server (`parlament-mcp`, `register-mcp`, …), suggest that instead of growing this one.

## Pull requests

Follow Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) and update `CHANGELOG.md` under `[Unreleased]`.

## The live suite: when it runs, and who sees a red result

**Cadence:** every Monday at 04:33 UTC, plus on demand via *Actions → Live-Tests → Run
workflow*. See [`.github/workflows/live-tests.yml`](.github/workflows/live-tests.yml).

**Who sees it:** A red run opens an issue labelled `upstream` and the stable title “Live-Tests gegen cms.lobbywatch.ch rot (<Datum>)”. A second red run recognises the open issue by its title prefix and appends to that same thread rather than opening a second one. Once the suite is green again, the issue closes itself.

**Three answers, not two.** `scripts/classify_live_run.py` reads the JUnit XML rather than
the exit code and separates `clear` (ran, green), `finding` (ran, something
fell) and `unknown` (did not run — install failed, nothing collected,
everything skipped). An `unknown` never closes an issue: closing would claim a
comparison that never happened.

**A red live run does not necessarily mean *our* bug.** It means the contract
with the source has changed, or the source is down. Both belong seen; only the
first belongs fixed. Please read the run before disabling the job — that is how
this check dies, and it is the only one in the repository that can contradict a
wrong assumption about cms.lobbywatch.ch. Every other test asserts against a fixture, and
the fixture was written from the same assumption as the code.
