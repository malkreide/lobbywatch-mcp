"""Unit tests for LobbywatchClient (respx-mocked HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
import respx

import lobbywatch_mcp.client as client_mod
from lobbywatch_mcp.client import LobbywatchClient, _is_forbidden_address, _ssrf_guard
from lobbywatch_mcp.config import API_BASE, DUMP_URL


@respx.mock
async def test_dump_download_and_parse(tmp_path: Path, dump_zip_bytes: bytes) -> None:
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=dump_zip_bytes))

    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()

    records = await client.all_parlamentarier()
    assert len(records) == 3
    assert records[0]["anzeige_name"] == "Mustermann, Anna"
    await client.aclose()


async def test_find_by_id(primed_client: LobbywatchClient) -> None:
    r = await primed_client.find_parlamentarier(2)
    assert r is not None
    assert r["anzeige_name"] == "Beispiel, Beat"


async def test_find_by_name_exact(primed_client: LobbywatchClient) -> None:
    r = await primed_client.find_parlamentarier("Mustermann, Anna")
    assert r is not None
    assert r["id"] == 1


async def test_find_by_name_fuzzy(primed_client: LobbywatchClient) -> None:
    r = await primed_client.find_parlamentarier("Mustermann")
    assert r is not None
    assert r["id"] == 1


async def test_find_returns_none_on_miss(primed_client: LobbywatchClient) -> None:
    r = await primed_client.find_parlamentarier("Nonexistent Person")
    assert r is None


@respx.mock
async def test_fetch_lobbygruppe_by_id(tmp_path: Path) -> None:
    respx.get(f"{API_BASE}/table/interessengruppe/aggregated/id/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {"id": 1, "anzeige_name": "Beispielgruppe", "organisationen": []},
            },
        )
    )

    client = LobbywatchClient(cache_dir=tmp_path)
    result = await client.fetch_lobbygruppe(1)
    assert result is not None
    assert result["anzeige_name"] == "Beispielgruppe"
    await client.aclose()


@pytest.mark.parametrize(
    "ip,forbidden",
    [
        ("169.254.169.254", True),  # AWS / GCP metadata
        ("127.0.0.1", True),
        ("10.0.0.5", True),
        ("192.168.1.1", True),
        ("172.16.0.1", True),
        ("::1", True),
        ("8.8.8.8", False),  # public DNS
        ("1.1.1.1", False),
    ],
)
def test_ssrf_guard_classifies_addresses(ip: str, forbidden: bool) -> None:
    """SEC-005: forbidden CIDRs must be flagged."""
    assert _is_forbidden_address(ip) is forbidden


async def test_ssrf_guard_blocks_metadata_ip() -> None:
    """SEC-005: an httpx request to a literal forbidden IP raises before connecting."""
    request = httpx.Request("GET", "http://169.254.169.254/latest/meta-data/")
    with pytest.raises(RuntimeError, match="forbidden address"):
        await _ssrf_guard(request)


@respx.mock
async def test_dump_download_retries_on_503(
    tmp_path: Path, dump_zip_bytes: bytes, monkeypatch
) -> None:
    """A transient 503 must be retried; the second attempt succeeds."""
    # Short-circuit the backoff sleep so the test stays fast.
    import lobbywatch_mcp.client as client_mod

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_mod.asyncio, "sleep", _instant)

    respx.get(DUMP_URL).mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, content=dump_zip_bytes),
        ]
    )

    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()
    records = await client.all_parlamentarier()
    assert len(records) == 3
    await client.aclose()


# --- Retry policy: Retry-After, jitter, and the cap --------------------------
# Adopted together with the hardened retry from the mcp-data-source-probe
# reference template. These assert the behaviour, not the constants: a
# deterministic ladder and an unread `Retry-After` are what a sweep across
# eleven servers found on 2026-08-03, and every one of them looked fine.


def _retry_after_error(value: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid/")
    return httpx.HTTPStatusError(
        "",
        request=request,
        response=httpx.Response(429, headers={"Retry-After": value}, request=request),
    )


def test_retry_after_reads_both_rfc9110_forms() -> None:
    def resp(status: int, headers: dict[str, str]) -> httpx.Response:
        request = httpx.Request("GET", "https://example.invalid/")
        return httpx.Response(status, headers=headers, request=request)

    assert client_mod.parse_retry_after(resp(429, {"Retry-After": "120"})) == 120.0

    later = format_datetime(datetime.now(UTC) + timedelta(seconds=90))
    seconds = client_mod.parse_retry_after(resp(503, {"Retry-After": later}))
    assert seconds is not None and 80 < seconds <= 90

    # A date in the past means "now", never a negative wait.
    past = "Wed, 21 Oct 2020 07:28:00 GMT"
    assert client_mod.parse_retry_after(resp(503, {"Retry-After": past})) == 0.0

    # Unparseable falls back to the curve. It must not crash on the error path,
    # which is the one path already going badly.
    assert client_mod.parse_retry_after(resp(429, {"Retry-After": "bald"})) is None
    assert client_mod.parse_retry_after(resp(429, {})) is None

    # 500 does not carry a meaningful Retry-After.
    assert client_mod.parse_retry_after(resp(500, {"Retry-After": "120"})) is None
    assert client_mod.parse_retry_after(None) is None


def test_backoff_is_jittered() -> None:
    delays = {client_mod.compute_delay(3, None) for _ in range(300)}
    # attempt 3 -> 2 * 2**2 = 8s, spread into [0.5x, 1.5x]
    assert len(delays) > 1, "a deterministic ladder synchronises every client"
    assert min(delays) >= 4.0
    assert max(delays) <= 12.0


def test_cap_binds_after_the_jitter() -> None:
    # Capping first and then multiplying by up to 1.5 would land at 30s, and
    # the constant would claim a ceiling it does not hold.
    deep = {client_mod.compute_delay(9, None) for _ in range(200)}
    assert max(deep) <= client_mod.RETRY_MAX_DELAY

    hinted = _retry_after_error("600")
    assert {client_mod.compute_delay(1, hinted) for _ in range(100)} == {client_mod.RETRY_MAX_DELAY}


def test_retry_after_jitter_is_one_sided() -> None:
    """The source said when. Later is polite; earlier ignores the value read."""
    delays = {client_mod.compute_delay(1, _retry_after_error("4")) for _ in range(300)}
    assert min(delays) >= 4.0, "never earlier than the source asked for"
    assert max(delays) <= 5.0  # 4 * 1.25
