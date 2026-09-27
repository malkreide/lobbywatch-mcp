"""Spec 2026-07-28 nativ: was ein Client der modernen Aera tatsaechlich bekommt.

`test_protocol_version.py` pinnt die SDK-Konstanten. Hier steht der gemessene
Teil, den jene Datei als fehlend benannte: Anfragen durch die zusammengebaute
ASGI-App (`build_asgi_app`) und durch einen echten `Client` in beiden Aeren.

Anlass war ein stiller Ausfall. `lobbywatch_refresh_dump` meldete seinen
Fortschritt per `ctx.info()`. Logging ist seit 2026-07-28 abgekuendigt
(SEP-2577) und wird dort nur ausgeliefert, wenn die Anfrage per `_meta` einen
Log-Level anfordert. Nachgemessen vor der Umstellung, derselbe Aufruf mit
`logging_callback`:

    legacy      -> 2 Meldungen
    2026-07-28  -> 0 Meldungen, kein Fehler, keine Warnung beim Client

Nichts war rot, weil kein Test das Werkzeug mit einem Client aufrief.
"""

from __future__ import annotations

import json
import time
import warnings
from typing import Any

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPDeprecationWarning
from mcp.types.version import LATEST_HANDSHAKE_VERSION, LATEST_MODERN_VERSION
from mcp_types import CLIENT_CAPABILITIES_META_KEY, PROTOCOL_VERSION_META_KEY
from starlette.testclient import TestClient

from lobbywatch_mcp.__main__ import build_asgi_app
from lobbywatch_mcp._version import PACKAGE_VERSION
from lobbywatch_mcp.client import LobbywatchClient
from lobbywatch_mcp.server import build_server
from tests.conftest import FIXTURE_RECORDS

MODES = ("legacy", LATEST_MODERN_VERSION)

# Der Host, unter dem `build_asgi_app` ohne `LOBBYWATCH_MCP_ALLOWED_HOSTS`
# erreichbar ist; der TestClient-Default `testserver` bekommt 421.
BASE_URL = "http://127.0.0.1:8000"
ACCEPT = {"Accept": "application/json, text/event-stream"}


async def _fake_load(self: LobbywatchClient, force: bool = False) -> None:
    """Ersetzt den Download (~17 MB) durch die Fixture — kein Netz im Test."""
    self._records = FIXTURE_RECORDS  # type: ignore[attr-defined]
    self._loaded_at = time.time()  # type: ignore[attr-defined]


@pytest.mark.parametrize("mode", MODES)
async def test_refresh_dump_meldet_fortschritt_in_beiden_aeren(
    mode: str, primed_client: LobbywatchClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Die Zusicherung, die vorher in der modernen Aera gebrochen war."""
    monkeypatch.setattr(LobbywatchClient, "ensure_dump_loaded", _fake_load)
    progress: list[tuple[float, float | None, str | None]] = []

    async def on_progress(p: float, total: float | None, message: str | None) -> None:
        progress.append((p, total, message))

    async with Client(build_server(client=primed_client), mode=mode) as client:
        assert client.protocol_version == (
            LATEST_HANDSHAKE_VERSION if mode == "legacy" else LATEST_MODERN_VERSION
        )
        result = await client.call_tool(
            "lobbywatch_refresh_dump", {}, progress_callback=on_progress
        )

    assert not result.is_error
    assert [p for p, _, _ in progress] == [0, 1], progress
    assert all(total == 1 for _, total, _ in progress)
    assert "Dump refreshed: 3 parliamentarians" in (progress[-1][2] or "")


async def test_kein_werkzeug_ruft_eine_abgekuendigte_api(
    primed_client: LobbywatchClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Jedes Werkzeug einmal in der modernen Aera, Abkuendigungen als Fehler.

    Eine `MCPDeprecationWarning` im Handler wird so zum `isError` der Antwort
    statt zu einer Zeile im Log, die niemand liest.
    """
    monkeypatch.setattr(LobbywatchClient, "ensure_dump_loaded", _fake_load)

    async def fake_lobbygruppe(self: LobbywatchClient, name_or_id: str) -> None:
        return None

    monkeypatch.setattr(LobbywatchClient, "fetch_lobbygruppe", fake_lobbygruppe)
    calls: dict[str, dict[str, Any]] = {
        "lobbywatch_get_parlamentarier": {"name_or_id": "Mustermann"},
        "lobbywatch_list_interessenbindungen": {"name_or_id": "1"},
        "lobbywatch_search_parlamentarier_nach_branche": {"branche_query": "Bildung"},
        "lobbywatch_get_lobbygruppe": {"name_or_id": "economiesuisse"},
        "lobbywatch_get_ranking": {},
        "lobbywatch_get_transparenzquote": {},
        "lobbywatch_refresh_dump": {},
        "lobbywatch_dump_status": {},
    }
    with warnings.catch_warnings():
        warnings.simplefilter("error", MCPDeprecationWarning)
        async with Client(build_server(client=primed_client), mode=LATEST_MODERN_VERSION) as c:
            listed = {t.name for t in (await c.list_tools()).tools}
            assert listed == set(calls), "neues Werkzeug? hier aufnehmen"
            for name, args in calls.items():
                result = await c.call_tool(name, args)
                assert not result.is_error, (name, result.content)


# ---------------------------------------------------------------------------
# Gemessen durch den HTTP-Stack
# ---------------------------------------------------------------------------


def _modern_post(http: TestClient, method: str, params: dict[str, Any], name: str | None = None):
    headers = {**ACCEPT, "Mcp-Protocol-Version": LATEST_MODERN_VERSION, "Mcp-Method": method}
    if name is not None:
        headers["Mcp-Name"] = name
    meta = {PROTOCOL_VERSION_META_KEY: LATEST_MODERN_VERSION, CLIENT_CAPABILITIES_META_KEY: {}}
    params = {**params, "_meta": {**params.get("_meta", {}), **meta}}
    return http.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


def _sse_messages(body: str) -> list[dict[str, Any]]:
    return [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]


@pytest.fixture
def http() -> TestClient:
    with TestClient(build_asgi_app("http"), base_url=BASE_URL) as client:
        yield client


def test_server_discover_ueber_http(http: TestClient) -> None:
    """Der Einstieg der modernen Aera: kein `initialize`, keine Session."""
    resp = _modern_post(http, "server/discover", {})

    assert resp.status_code == 200, resp.text
    assert "mcp-session-id" not in resp.headers
    result = resp.json()["result"]
    assert LATEST_MODERN_VERSION in result["supportedVersions"]
    assert result["ttlMs"] > 0 and result["cacheScope"] == "public"
    # Vorher "": `MCPServer(version=...)` fehlte, und unter 2026-07-28 steht
    # der Stempel im `_meta` jeder Antwort.
    info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
    assert info == {"name": "lobbywatch-mcp", "version": PACKAGE_VERSION}


def test_initialize_deckelt_bei_der_handshake_version(http: TestClient) -> None:
    """Die Aushandlung der Legacy-Aera, gemessen statt aus Konstanten gelesen.

    Ein Client, der eine unbekannte, neuere Revision verlangt, bekommt die
    Handshake-Decke — nicht 2026-07-28, das ueber `initialize` nicht erreichbar
    ist.
    """
    resp = http.post(
        "/mcp",
        headers=ACCEPT,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2099-01-01",
                "capabilities": {},
                "clientInfo": {"name": "probe", "version": "0"},
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.headers.get("mcp-session-id"), "die Handshake-Aera traegt eine Session"
    (message,) = _sse_messages(resp.text)
    assert message["result"]["protocolVersion"] == LATEST_HANDSHAKE_VERSION
    assert message["result"]["serverInfo"]["version"] == PACKAGE_VERSION


def test_refresh_dump_fortschritt_erreicht_den_http_stream(
    http: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Derselbe Fix auf dem Draht: `notifications/progress` im SSE-Strom der
    Antwort, vor dem Resultat."""
    monkeypatch.setattr(LobbywatchClient, "ensure_dump_loaded", _fake_load)
    resp = _modern_post(
        http,
        "tools/call",
        {"name": "lobbywatch_refresh_dump", "arguments": {}, "_meta": {"progressToken": "t1"}},
        name="lobbywatch_refresh_dump",
    )

    assert resp.status_code == 200, resp.text
    messages = _sse_messages(resp.text)
    progress = [m for m in messages if m.get("method") == "notifications/progress"]
    assert [m["params"]["progress"] for m in progress] == [0, 1], messages
    assert all(m["params"]["progressToken"] == "t1" for m in progress)
    assert messages[-1]["result"]["isError"] is False
