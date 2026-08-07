"""Data access layer for lobbywatch-mcp.

Design: dump-first, API-fallback.

Rationale (verified live on 2026-04-21):
    * The weekly aggregated JSON dump is stable, contains 245 parliamentarians
      with 113 scalar fields and 7'780 interessenbindungen total, and is
      refreshed every Monday morning by Lobbywatch.
    * The live dataIF REST API currently returns 0 records for the
      ``/table/parlamentarier/...`` endpoints. Other tables (interessengruppe,
      branche) work. So we use the dump for parliamentarian queries and fall
      back to the live API only for lobby groups and search.
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import json
import logging
import random
import time
import zipfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from lobbywatch_mcp.config import (
    API_BASE,
    CACHE_DIR,
    CACHE_TTL_SECONDS,
    DUMP_INNER_FILE,
    DUMP_URL,
    HTTP_TIMEOUT_SECONDS,
    USER_AGENT,
)

logger = logging.getLogger(__name__)


# --- Retry policy ------------------------------------------------------------
# Adopted from the mcp-data-source-probe reference template (repaired
# 2026-08-07). Three questions: *what* is retried, *how fast*, and *how long*.
# The first is settled in the retry loop (4xx except 429 fails fast); these
# settle the other two.

RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY = 2.0  # ladder before jitter: 2, 4, 8

# Ceiling on the WHOLE call — every attempt and every wait together. An attempt
# count is not a bound: four attempts against an upstream that takes 30s to time
# out is two minutes inside one tool call, and the number never says so. The
# anchor is measured, not guessed: the Python MCP SDK ships
# MCP_DEFAULT_TIMEOUT = 30.0, so 25s leaves headroom for framing and parsing.
RETRY_TOTAL_BUDGET = 25.0

# Ceiling for a single wait. Bounds the exponential ladder, and bounds a
# `Retry-After` the source may send but we are not obliged to sit through.
RETRY_MAX_DELAY = 20.0

# Jitter spread. Without it every client that hit the same outage retries in
# lockstep, and the load returns as a wave exactly when the source recovers —
# the retry storm extends the outage it was meant to bridge.
RETRY_JITTER_SPREAD = 0.5  # exponential delays land in [0.5x, 1.5x]

# On a `Retry-After`, deliberately one-sided: the source said when to come back,
# so coming back later is fine and coming back earlier is not.
RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses that carry a meaningful `Retry-After` (RFC 9110 section 10.2.3).
RETRY_AFTER_STATUSES = frozenset({429, 503})


class UpstreamUnavailableError(Exception):
    """No request was attempted — the budget was gone before the first try.

    A named type rather than ``RuntimeError``: a caller can branch on this, and
    cannot tell a bare ``RuntimeError`` apart from a bug in this server's own
    code. Raised only when there is no upstream exception to re-raise.
    """


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or ``None``.

    RFC 9110 section 10.2.3 allows two forms — delta-seconds (``120``) and an
    HTTP-date (``Wed, 21 Oct 2026 07:28:00 GMT``). Both appear in the wild, so
    both are read. Anything unparseable yields ``None`` and the caller falls
    back to its own curve: a malformed header must not become a crash on the
    error path, which is the one path already going badly.
    """
    if resp is None or resp.status_code not in RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def compute_delay(attempt: int, last_error: Exception | None) -> float:
    """Seconds to wait before ``attempt`` (1-based for the first retry).

    The source's own answer beats our guess: a ``Retry-After`` on a 429 or 503
    wins over the exponential curve. Everything is spread, then capped.

    The cap wraps the jitter and not the other way round. ``min(cap, base) *
    jitter`` and ``min(cap, base * jitter)`` both contain a cap and a jitter;
    only the second is bounded — a value capped at 20s and then multiplied by
    up to 1.5 lands at 30s, and the constant would claim a ceiling it does not
    hold.
    """
    hinted = parse_retry_after(getattr(last_error, "response", None))
    if hinted is not None:
        return min(
            hinted * (1.0 + random.random() * RETRY_AFTER_JITTER),
            RETRY_MAX_DELAY,
        )
    return min(
        RETRY_BASE_DELAY
        * 2 ** (attempt - 1)
        * (1.0 - RETRY_JITTER_SPREAD + random.random() * 2 * RETRY_JITTER_SPREAD),
        RETRY_MAX_DELAY,
    )


# Networks an outbound MCP request must never reach: RFC1918 / link-local /
# loopback / cloud-metadata. Pre-built once because each request goes through
# the SSRF guard hook below (audit SEC-005).
_SSRF_FORBIDDEN_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",  # link-local incl. cloud metadata (169.254.169.254)
        "127.0.0.0/8",
        "0.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _is_forbidden_address(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return any(addr in net for net in _SSRF_FORBIDDEN_NETWORKS)


async def _ssrf_guard(request: httpx.Request) -> None:
    """httpx event hook: refuse requests whose host resolves to a private,
    link-local, or loopback address (audit SEC-005, defense-in-depth against
    DNS rebinding / SSRF).

    The host is already constrained by the hardcoded ``API_BASE`` /
    ``DUMP_URL`` constants, but the resolver could still drift between
    process start and any individual request — this hook catches that.
    """
    host = request.url.host
    if not host:
        return
    # Allow literal IP URLs only if they are not in a forbidden network.
    try:
        ipaddress.ip_address(host)
        if _is_forbidden_address(host):
            raise RuntimeError(f"Refusing to connect to forbidden address {host}")
        return
    except ValueError:
        pass  # not a literal IP — resolve below

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
    except OSError:
        # Resolver failure: let httpx surface its own error rather than
        # masking it here.
        return
    resolved = sorted({info[4][0] for info in infos})
    bad = [ip for ip in resolved if _is_forbidden_address(ip)]
    if bad:
        logger.error(
            "SSRF guard blocked %s — resolved to forbidden addresses %s",
            host,
            bad,
        )
        raise RuntimeError(f"Refusing to connect to {host}: resolved to forbidden addresses {bad}")


class LobbywatchClient:
    """Access layer around the weekly dump and the live dataIF."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_seconds: int = CACHE_TTL_SECONDS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cache_dir = cache_dir or CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._dump_path = self._cache_dir / "aggregated.json"
        self._records: list[dict[str, Any]] | None = None
        self._loaded_at: float | None = None
        self._lock = asyncio.Lock()
        self._http = http_client or httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=False,
            event_hooks={"request": [_ssrf_guard]},
        )
        self._owns_http = http_client is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Dump handling
    # ------------------------------------------------------------------

    async def ensure_dump_loaded(self, force: bool = False) -> None:
        """Download, cache, and load the weekly JSON dump if needed."""
        async with self._lock:
            if not force and self._records is not None and self._is_fresh():
                return

            if force or not self._dump_path.exists() or self._file_stale(self._dump_path):
                await self._download_dump()

            self._records = self._parse_dump(self._dump_path)
            self._loaded_at = time.time()
            logger.info("Dump loaded: %d parliamentarians", len(self._records))

    def _is_fresh(self) -> bool:
        return self._loaded_at is not None and (time.time() - self._loaded_at) < self._ttl

    def _file_stale(self, path: Path) -> bool:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return True
        return age > self._ttl

    async def _download_dump(self) -> None:
        """Download the weekly dump with jittered backoff and a time budget.

        The Lobbywatch CMS occasionally returns HTTP 503 during maintenance
        windows, and a 503 is the one status that answers the question the
        backoff curve otherwise guesses at — see ``parse_retry_after``.
        """
        deadline = time.monotonic() + RETRY_TOTAL_BUDGET
        last_error: Exception | None = None
        resp: httpx.Response | None = None

        for attempt in range(RETRY_ATTEMPTS):
            if attempt > 0:
                delay = compute_delay(attempt, last_error)
                # A wait that outlasts the budget is a wait for nobody: the
                # caller has given up by the time it ends. Stop instead.
                if delay >= deadline - time.monotonic():
                    break
                logger.warning(
                    "Dump download attempt %d failed (%s); retrying in %.1fs",
                    attempt,
                    type(last_error).__name__ if last_error else "?",
                    delay,
                )
                await asyncio.sleep(delay)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                logger.info("Downloading Lobbywatch dump from %s", DUMP_URL)
                # httpx bounds each operation and its read timeout restarts
                # with every chunk — a slowly trickling dump can outlast the
                # budget without a single read expiring. `asyncio.timeout` is
                # the wall-clock deadline the budget actually promises.
                async with asyncio.timeout(remaining):
                    resp = await self._http.get(DUMP_URL)
                    resp.raise_for_status()
                break
            except TimeoutError as exc:  # the budget is gone, not just this try
                last_error = exc
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                # 4xx responses other than 429 should not be retried.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status != 429:
                    raise

        if resp is None:
            if last_error is None:
                raise UpstreamUnavailableError(
                    f"no attempt made: the {RETRY_TOTAL_BUDGET:g}s budget was "
                    f"already spent (host={urlsplit(DUMP_URL).hostname})"
                )
            # Re-raised, not wrapped. `httpx.ConnectTimeout`, `ReadTimeout` and
            # `ConnectError` carry an EMPTY ``str()`` and are the only errors a
            # real outage produces; a wrapper hands the caller a message with
            # nothing in it and takes away the type it could have branched on.
            logger.error(
                "Lobbywatch dump unreachable: %s (host=%s)",
                type(last_error).__name__,
                urlsplit(DUMP_URL).hostname,
            )
            raise last_error

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # The dump contains a few files; we want the essential nested variant.
            inner_name = DUMP_INNER_FILE
            if inner_name not in zf.namelist():
                # Some weeks ship slightly different inner names — take the first
                # JSON with "parlamentarier_nested" in it.
                candidates = [
                    n for n in zf.namelist() if n.endswith(".json") and "parlamentarier_nested" in n
                ]
                if not candidates:
                    logger.error("Dump archive members: %s", zf.namelist())
                    raise RuntimeError("Lobbywatch dump format unexpected")
                inner_name = candidates[0]
            with zf.open(inner_name) as src, self._dump_path.open("wb") as dst:
                dst.write(src.read())

    @staticmethod
    def _parse_dump(path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("Unexpected dump shape: %s", type(data).__name__)
            raise RuntimeError("Lobbywatch dump shape invalid")
        return data

    # ------------------------------------------------------------------
    # Accessors (dump-based)
    # ------------------------------------------------------------------

    async def all_parlamentarier(self) -> list[dict[str, Any]]:
        await self.ensure_dump_loaded()
        assert self._records is not None
        return self._records

    async def find_parlamentarier(self, id_or_name: int | str) -> dict[str, Any] | None:
        records = await self.all_parlamentarier()
        if isinstance(id_or_name, int) or (isinstance(id_or_name, str) and id_or_name.isdigit()):
            wanted = int(id_or_name)
            for r in records:
                if r.get("id") == wanted:
                    return r
            return None

        # String search: try exact anzeige_name, then fuzzy on nachname/vorname.
        from rapidfuzz import fuzz, process

        query = str(id_or_name).strip().lower()

        exact = [r for r in records if (r.get("anzeige_name", "") or "").lower() == query]
        if exact:
            return exact[0]

        names = [(r.get("anzeige_name") or "", r) for r in records]
        best = process.extractOne(query, [n for n, _ in names], scorer=fuzz.WRatio, score_cutoff=70)
        if not best:
            return None
        _matched_name, _score, idx = best
        return names[idx][1]

    async def find_candidates(
        self,
        query: str,
        *,
        min_score: int = 50,
        max_score_excl: int = 70,
        top_k: int = 3,
    ) -> list[tuple[dict[str, Any], int]]:
        """Return up to ``top_k`` near-miss parliamentarian records ranked by
        rapidfuzz WRatio (audit ARCH-003 — avoid the silent "not found" by
        offering "did you mean…?" candidates).

        Only results in ``[min_score, max_score_excl)`` are returned: the
        upper bound stays below ``find_parlamentarier``'s 70 threshold so
        these are *misses*, not silently competing matches.
        """
        if not query.strip() or query.isdigit():
            return []
        from rapidfuzz import fuzz, process

        records = await self.all_parlamentarier()
        names = [(r.get("anzeige_name") or "", r) for r in records]
        candidates = process.extract(
            query.strip().lower(),
            [n for n, _ in names],
            scorer=fuzz.WRatio,
            limit=top_k,
            score_cutoff=min_score,
        )
        return [
            (names[idx][1], int(score))
            for _name, score, idx in candidates
            if score < max_score_excl
        ]

    async def status(self) -> dict[str, Any]:
        loaded = self._records is not None
        age = int(time.time() - self._loaded_at) if self._loaded_at else None
        return {
            "loaded": loaded,
            "age_seconds": age,
            "record_count": len(self._records) if self._records else 0,
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._loaded_at))
            if self._loaded_at
            else None,
        }

    # ------------------------------------------------------------------
    # Live dataIF (fallback path)
    # ------------------------------------------------------------------

    async def api_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{API_BASE}/{path.lstrip('/')}"
        resp = await self._http.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def fetch_lobbygruppe(self, id_or_name: int | str) -> dict[str, Any] | None:
        """Use the live dataIF — this endpoint was verified working."""
        if isinstance(id_or_name, int) or (isinstance(id_or_name, str) and id_or_name.isdigit()):
            data = await self.api_get(f"table/interessengruppe/aggregated/id/{int(id_or_name)}")
            return data.get("data")

        # Search by name first, then fetch aggregated. URL-encode user input to
        # prevent path traversal — the host is hardcoded but path segments still
        # warrant escaping (audit SEC-004).
        search = await self.api_get(
            f"search/default/{quote(str(id_or_name), safe='')}",
            params={"limit": 5},
        )
        hits = search.get("data") or []
        for hit in hits:
            if hit.get("table") == "interessengruppe":
                data = await self.api_get(f"table/interessengruppe/aggregated/id/{hit.get('id')}")
                return data.get("data")
        return None
