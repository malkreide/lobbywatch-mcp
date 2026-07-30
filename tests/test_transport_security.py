"""Inbound Host/Origin check for the HTTP transports (SEC-005, inbound half).

The trigger was not a missing guard but an over-strict one aimed at the wrong
address. mcp 2.x auto-enables an allow-list of ``127.0.0.1:*`` when the app's
``host`` argument looks like loopback, and ``streamable_http_app()`` /
``sse_app()`` default that argument to ``127.0.0.1``. A server started with
``LOBBYWATCH_MCP_HOST=0.0.0.0`` therefore answered every request under a real
hostname with HTTP 421.

Before the migration to mcp 2.x, ``host`` reached the ``FastMCP`` constructor,
where the same auto-enable logic saw the real bind and correctly left protection
off. The migration moved ``host`` to a per-app kwarg and stopped passing it.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from lobbywatch_mcp.__main__ import _run_asgi, build_transport_security

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def test_loopback_bind_is_protected(monkeypatch):
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    sec = build_transport_security("127.0.0.1", 8000)
    assert sec is not None
    assert sec.enable_dns_rebinding_protection is True
    assert "127.0.0.1:8000" in sec.allowed_hosts


def test_wildcard_bind_without_allowlist_stays_off(monkeypatch):
    """The actual fix.

    On 0.0.0.0 the reachable name is unknown here, and the SDK's loopback
    default is precisely a guess — it reproduces the 421. So protection stays
    off and the caller warns.
    """
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    assert build_transport_security("0.0.0.0", 8000) is None


def test_wildcard_bind_with_allowlist_is_protected(monkeypatch):
    monkeypatch.setenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", "lobby.example.ch")
    sec = build_transport_security("0.0.0.0", 8000)
    assert sec is not None
    assert "lobby.example.ch" in sec.allowed_hosts
    # Loopback stays in, or container health checks break.
    assert "127.0.0.1:8000" in sec.allowed_hosts


def test_cors_origins_pass_the_transport_check(monkeypatch):
    """Otherwise the transport rejects exactly the browser clients CORS allows."""
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("LOBBYWATCH_MCP_CORS_ORIGINS", "https://claude.ai")
    sec = build_transport_security("127.0.0.1", 8000)
    assert "https://claude.ai" in sec.allowed_origins


def test_wildcard_cors_is_not_copied(monkeypatch):
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("LOBBYWATCH_MCP_CORS_ORIGINS", "*")
    sec = build_transport_security("127.0.0.1", 8000)
    assert "*" not in sec.allowed_origins


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_all_loopback_forms_count_as_local(host, monkeypatch):
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    assert build_transport_security(host, 8000) is not None


def _app(monkeypatch, transport: str, host: str, port: int = 8000):
    """Build the app exactly as `_run_asgi` does, without starting uvicorn."""
    import uvicorn

    captured: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(app=app, **kw))
    _run_asgi(transport, host, port)
    return captured


def _post(app, host_header: str) -> int:
    with TestClient(app) as client:
        return client.post(
            "/mcp", headers={"Host": host_header, **_HEADERS}, json=_INIT
        ).status_code


def test_a_public_bind_is_reachable_again(monkeypatch):
    """The regression itself, through the real ASGI stack.

    Without the `host` kwarg this is a 421 — the state this commit repairs.
    """
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("LOBBYWATCH_MCP_CORS_ORIGINS", raising=False)
    app = _app(monkeypatch, "http", "0.0.0.0")["app"]
    assert _post(app, "lobby.example.ch") == 200


def test_configured_host_is_served(monkeypatch):
    monkeypatch.setenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", "lobby.example.ch")
    monkeypatch.delenv("LOBBYWATCH_MCP_CORS_ORIGINS", raising=False)
    app = _app(monkeypatch, "http", "0.0.0.0")["app"]
    assert _post(app, "lobby.example.ch") == 200


def test_foreign_host_is_rejected(monkeypatch):
    monkeypatch.setenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", "lobby.example.ch")
    monkeypatch.delenv("LOBBYWATCH_MCP_CORS_ORIGINS", raising=False)
    app = _app(monkeypatch, "http", "0.0.0.0")["app"]
    assert _post(app, "evil.example.com") == 421


def test_right_host_wrong_port_is_rejected(monkeypatch):
    """The load-bearing case.

    ``evil.example.com`` alone proves little: a fallback loopback policy would
    reject it too. Only "right hostname, wrong port" separates a port-exact
    allow-list from one that permits anything — and it fails the moment
    ``transport_security`` stops being passed.
    """
    monkeypatch.setenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", "lobby.example.ch:8000")
    monkeypatch.delenv("LOBBYWATCH_MCP_CORS_ORIGINS", raising=False)
    app = _app(monkeypatch, "http", "0.0.0.0")["app"]
    assert _post(app, "lobby.example.ch:9999") == 421


def test_the_bind_reaches_uvicorn_too(monkeypatch):
    """The app and the listener must agree, or the allow-list guards the wrong
    address while uvicorn binds another."""
    monkeypatch.delenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", raising=False)
    captured = _app(monkeypatch, "http", "0.0.0.0", 9100)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9100
