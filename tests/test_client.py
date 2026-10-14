"""Unit tests for LobbywatchClient (respx-mocked HTTP)."""

from __future__ import annotations

import inspect
import io
import json
import os
import time
import zipfile
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest
import respx

import lobbywatch_mcp.client as client_mod
from lobbywatch_mcp.client import LobbywatchClient, _is_forbidden_address, _ssrf_guard
from lobbywatch_mcp.config import API_BASE, DUMP_INNER_FILE, DUMP_URL
from tests.conftest import FIXTURE_RECORDS


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

    monkeypatch.setattr(client_mod, "_sleep", _instant)

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


# --- Die Naht, und warum sie nicht `asyncio.sleep` ist -----------------------


def test_der_retry_geht_ueber_den_alias():
    """Sonst patchen die Tests eine Naht, die der Code gar nicht benutzt.

    Umgeht das Modul den Alias, bleibt der Patch wirkungslos und die Suite
    wartet die echte Backoff-Leiter ab. Kein Test faellt dabei — sie wird nur
    um ein Vielfaches langsamer, und eine laengere Laufzeit ist kein Signal,
    das jemand liest. Diese Zusicherung macht daraus einen Fehlschlag.
    """
    quelle = inspect.getsource(client_mod)
    assert "await _sleep(" in quelle, "der Retry ruft den Modul-Alias nicht mehr auf"
    assert "await asyncio.sleep(" not in quelle, "der Retry umgeht den Alias"


# --- Die Quelle antwortet, aber nicht mit einem ZIP --------------------------
# Live-Lauf vom 12.10.2026 (Issue #74): HTTP 200, `resp.content` kein ZIP, und
# zur selben Sekunde lieferte der dataIF fuer eine existierende ID keine Daten.
# Zwei Tage spaeter antworteten beide normal. Der rohe `zipfile.BadZipFile`
# sagte nur «File is not a zip file» — was stattdessen kam, liess sich nicht
# mehr feststellen.

_KEIN_ZIP = b"<!DOCTYPE html><html><body>Wartungsarbeiten</body></html>"


@respx.mock
async def test_dump_ohne_zip_ist_ein_benannter_quellfehler(tmp_path: Path) -> None:
    respx.get(DUMP_URL).mock(
        return_value=httpx.Response(
            200,
            content=_KEIN_ZIP,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Last-Modified": "Mon, 12 Oct 2026 12:21:00 GMT",
            },
        )
    )

    client = LobbywatchClient(cache_dir=tmp_path)
    with pytest.raises(client_mod.UpstreamFormatError) as exc_info:
        await client.ensure_dump_loaded()
    await client.aclose()

    msg = str(exc_info.value)
    # Was kam an — Status und Kopfzeilen, damit der naechste rote Lauf es sagt.
    assert "HTTP 200" in msg
    assert "text/html" in msg
    assert f"{len(_KEIN_ZIP)} bytes" in msg
    assert "Mon, 12 Oct 2026 12:21:00 GMT" in msg
    # Den Status, nicht den Antwortkoerper: der geht ungeprueft ans Modell.
    assert "Wartungsarbeiten" not in msg
    # Der Cache bleibt unberuehrt — kein halber Dump auf der Platte.
    assert not (tmp_path / "aggregated.json").exists()


# --- Stale-Cache-Fallback ------------------------------------------------------
# Scheitert die Aktualisierung, antwortet ein zwischengespeicherter Dump — aber
# nur, wenn er jung genug ist, nur ohne `force`, und nie stillschweigend:
# `stale_notice()` nennt Datenstand, Alter und Grund. Anlass war der Live-Lauf
# vom 12.10.2026: Ein Dump vom Vortag lag auf der Platte, und trotzdem fiel
# jede Abfrage zu Parlamentarierinnen und Parlamentariern aus.

_TAG = 24 * 60 * 60


def _zwischengespeichert(cache_dir: Path, alter_s: float) -> float:
    """Legt einen Dump mit gesetztem Alter in den Cache; gibt seine mtime zurueck."""
    path = cache_dir / "aggregated.json"
    path.write_text(json.dumps(FIXTURE_RECORDS), encoding="utf-8")
    mtime = time.time() - alter_s
    os.utime(path, (mtime, mtime))
    return mtime


_AUSFAELLE = {
    "kein_zip": httpx.Response(200, content=b"<html>Wartung</html>"),
    "http_404": httpx.Response(404),
    "verbindung": httpx.ConnectError("connection refused"),
}


@pytest.mark.parametrize("ausfall", sorted(_AUSFAELLE))
@respx.mock
async def test_zwischengespeicherter_dump_springt_ein(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ausfall: str
) -> None:
    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(client_mod, "_sleep", _instant)
    respx.get(DUMP_URL).mock(side_effect=lambda _req: _antwort(ausfall))
    mtime = _zwischengespeichert(tmp_path, 2 * _TAG)

    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()
    await client.aclose()

    assert len(await client.all_parlamentarier()) == len(FIXTURE_RECORDS)
    notice = client.stale_notice()
    assert notice is not None
    assert notice["cached_at"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))
    assert abs(notice["age_seconds"] - 2 * _TAG) < 60
    erwartet = {
        "kein_zip": "UpstreamFormatError",
        "http_404": "HTTPStatusError",
        "verbindung": "ConnectError",
    }[ausfall]
    assert notice["reason"].startswith(erwartet)


def _antwort(ausfall: str) -> httpx.Response:
    antwort = _AUSFAELLE[ausfall]
    if isinstance(antwort, Exception):
        raise antwort
    return antwort


@respx.mock
async def test_zu_alter_dump_springt_nicht_ein(tmp_path: Path) -> None:
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=b"kein zip"))
    _zwischengespeichert(tmp_path, 8 * _TAG)

    client = LobbywatchClient(cache_dir=tmp_path, stale_max_seconds=7 * _TAG)
    with pytest.raises(client_mod.UpstreamFormatError):
        await client.ensure_dump_loaded()
    await client.aclose()
    assert client.stale_notice() is None


@respx.mock
async def test_null_schaltet_den_fallback_ab(tmp_path: Path) -> None:
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=b"kein zip"))
    _zwischengespeichert(tmp_path, 2 * _TAG)

    client = LobbywatchClient(cache_dir=tmp_path, stale_max_seconds=0)
    with pytest.raises(client_mod.UpstreamFormatError):
        await client.ensure_dump_loaded()
    await client.aclose()


@respx.mock
async def test_ausdrueckliches_refresh_faellt_nie_zurueck(tmp_path: Path) -> None:
    """`lobbywatch_refresh_dump` meldete sonst einen Erfolg, den es nicht gab."""
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=b"kein zip"))
    _zwischengespeichert(tmp_path, 2 * _TAG)

    client = LobbywatchClient(cache_dir=tmp_path)
    with pytest.raises(client_mod.UpstreamFormatError):
        await client.ensure_dump_loaded(force=True)
    await client.aclose()
    assert client.stale_notice() is None


async def test_ssrf_sperre_wird_nicht_ueberdeckt(tmp_path: Path) -> None:
    """Eine gesperrte Adresse ist kein Ausfall, den alte Daten verdecken duerfen."""
    _zwischengespeichert(tmp_path, 2 * _TAG)
    client = LobbywatchClient(cache_dir=tmp_path)

    async def _gesperrt() -> None:
        raise RuntimeError("Refusing to connect to cms.lobbywatch.ch")

    client._download_dump = _gesperrt  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Refusing"):
        await client.ensure_dump_loaded()
    await client.aclose()


@respx.mock
async def test_nach_dem_wartefenster_wird_die_quelle_erneut_gefragt(
    tmp_path: Path, dump_zip_bytes: bytes
) -> None:
    route = respx.get(DUMP_URL).mock(
        side_effect=[
            httpx.Response(200, content=b"kein zip"),
            httpx.Response(200, content=dump_zip_bytes),
        ]
    )
    _zwischengespeichert(tmp_path, 2 * _TAG)
    client = LobbywatchClient(cache_dir=tmp_path)

    await client.ensure_dump_loaded()
    assert client.stale_notice() is not None
    assert route.call_count == 1

    # Innerhalb des Fensters: kein neuer Versuch — jeder kostet bis zum ganzen
    # Retry-Budget, und das zahlte sonst jede einzelne Abfrage.
    await client.ensure_dump_loaded()
    assert route.call_count == 1

    # Fenster abgelaufen — nicht erst nach der vollen TTL von 24 h.
    client._loaded_at -= client_mod.STALE_RETRY_SECONDS + 1  # type: ignore[operator]
    await client.ensure_dump_loaded()
    assert route.call_count == 2
    assert client.stale_notice() is None
    await client.aclose()


@respx.mock
async def test_frischer_dump_traegt_keinen_vermerk(tmp_path: Path, dump_zip_bytes: bytes) -> None:
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=dump_zip_bytes))
    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()
    await client.aclose()
    assert client.stale_notice() is None


@respx.mock
async def test_kaputtes_archiv_zerstoert_den_zwischenspeicher_nicht(tmp_path: Path) -> None:
    """Intaktes Verzeichnis, beschaedigter Inhalt — etwa eine Datei, die die
    Quelle gerade ueberschreibt. Der Cache wurde vor dem Lesen geleert, und
    damit fehlte genau die Kopie, die einspringen soll."""
    inner = json.dumps(FIXTURE_RECORDS).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(DUMP_INNER_FILE, inner)
    raw = bytearray(buf.getvalue())
    raw[raw.find(inner[:40])] ^= 0xFF  # CRC passt nicht mehr
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=bytes(raw)))
    _zwischengespeichert(tmp_path, 2 * _TAG)
    vorher = (tmp_path / "aggregated.json").read_bytes()

    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()
    await client.aclose()

    assert (tmp_path / "aggregated.json").read_bytes() == vorher
    notice = client.stale_notice()
    assert notice is not None
    assert notice["reason"].startswith("UpstreamFormatError")


@respx.mock
async def test_cache_wird_atomar_ersetzt(tmp_path: Path, dump_zip_bytes: bytes) -> None:
    """Ein Absturz mitten im Schreiben laesst sonst einen abgeschnittenen Cache
    zurueck, der nach seiner mtime frisch aussieht. Gemessen wird der Ersatz:
    `replace` bringt einen neuen Inode, Schreiben an Ort und Stelle nicht."""
    respx.get(DUMP_URL).mock(return_value=httpx.Response(200, content=dump_zip_bytes))
    _zwischengespeichert(tmp_path, 2 * _TAG)
    inode_vorher = (tmp_path / "aggregated.json").stat().st_ino

    client = LobbywatchClient(cache_dir=tmp_path)
    await client.ensure_dump_loaded()
    await client.aclose()

    assert (tmp_path / "aggregated.json").stat().st_ino != inode_vorher
    assert sorted(p.name for p in tmp_path.iterdir()) == ["aggregated.json"]
