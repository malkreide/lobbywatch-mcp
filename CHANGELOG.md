# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multi-stage `Dockerfile` and `.dockerignore` (audit SCALE-004). Runtime
  image runs as `uid 1000`, read-only-rootfs compatible, no build
  toolchain in the final stage (audit SEC-007).
- `deploy/docker-compose.example.yml` with hardening defaults:
  `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, tmpfs cache,
  loopback-only port bind, healthcheck, and `deploy.resources` limits
  (256 MiB / 0.1 CPU request, 512 MiB / 0.5 CPU limit) — audit SCALE-006.
- `docs/deployment.md`: trust-model recap, container build/run commands,
  resource-sizing rationale, HAProxy stick-table example for sticky LBs
  (audit SCALE-002, SCALE-003), and a Kubernetes egress `NetworkPolicy`
  template (audit SEC-021).

## [0.2.0] - 2026-05-09

### Changed (Breaking)
- **Tool names now carry a `lobbywatch_` namespace prefix** (audit SEC-022).
  All eight tools were renamed:
  `get_parlamentarier` → `lobbywatch_get_parlamentarier`,
  `list_interessenbindungen` → `lobbywatch_list_interessenbindungen`,
  `search_parlamentarier_nach_branche` → `lobbywatch_search_parlamentarier_nach_branche`,
  `get_lobbygruppe` → `lobbywatch_get_lobbygruppe`,
  `get_ranking` → `lobbywatch_get_ranking`,
  `get_transparenzquote` → `lobbywatch_get_transparenzquote`,
  `refresh_dump` → `lobbywatch_refresh_dump`,
  `dump_status` → `lobbywatch_dump_status`.
  Existing clients referencing the old names must be updated.

### Added
- FastMCP `lifespan` context manager owns the `LobbywatchClient` lifecycle
  (audit SDK-001). The shared `httpx.AsyncClient` is now closed cleanly on
  server shutdown; previously it leaked at process exit.
- Input validation at tool boundaries (audit SEC-018):
  `name_or_id` and `branche_query` bound to 1–200 chars; `kommission` /
  `partei` bound to ≤80 chars; `limit` bounded to 1–200 (search) /
  1–100 (ranking); `kriterium` is now a `Literal` enum so invalid values
  are rejected at the schema layer instead of via runtime `ValueError`.

### Changed
- `mcp[cli]` dependency is now bounded `<2.0.0` (audit ARCH-012).
- `USER_AGENT` bumped to `lobbywatch-mcp/0.2.0`.

## [0.1.0] - 2026-04-21

### Added
- Initial scaffold for `lobbywatch-mcp`, part of the Swiss Public Data MCP Portfolio.
- Hybrid data access: dump-first (weekly Lobbywatch JSON export) with live
  `dataIF` fallback for lobby groups.
- Phase 1 tools:
  - `get_parlamentarier` — profile lookup with fuzzy name match
  - `list_interessenbindungen` — conflict-of-interest records per MP
  - `search_parlamentarier_nach_branche` — branche + commission filter
  - `get_lobbygruppe` — live lobby group fetch via dataIF
  - `get_ranking` — top-N by criterion, commission/party filters
  - `get_transparenzquote` — distribution of verguetungstransparenz labels
  - `refresh_dump`, `dump_status` — cache control
- Retry + exponential backoff (2s/4s/8s) for dump downloads — tolerant of upstream HTTP 503 blips observed live.
- Dual transport: `stdio` (default) and `streamable-http` / `sse`.
- Pydantic v2 response envelopes carrying CC BY-SA 4.0 attribution.
- CI matrix (Python 3.11–3.13), ruff lint/format, respx-mocked unit tests.
- Tag-triggered PyPI publish workflow via OIDC Trusted Publisher.
- Live test suite (`@pytest.mark.live`) excluded from CI.

### Known limitations
- The upstream `/table/parlamentarier/...` dataIF endpoint returns empty
  responses at release time; all parliamentarian-facing tools therefore use
  the weekly dump. Lobby group lookups go through the live API.
- `zutrittsberechtigungen` are present in the data model but empty in the
  essential dump used here — surfaced as a stub for future expansion.
