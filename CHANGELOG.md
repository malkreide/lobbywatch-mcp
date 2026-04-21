# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
