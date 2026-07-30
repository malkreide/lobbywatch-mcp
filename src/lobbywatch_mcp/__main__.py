"""CLI entry point for lobbywatch-mcp.

Transport selection follows the Swiss Public Data MCP Portfolio convention:
set ``LOBBYWATCH_MCP_TRANSPORT`` to ``stdio`` (default), ``http`` or ``sse``.

Observability env vars (audit OBS-003, OBS-006):
    LOBBYWATCH_MCP_LOG_FORMAT    text | json    (default: text)
    LOBBYWATCH_MCP_LOG_LEVEL     DEBUG | INFO | WARNING | ERROR  (default: INFO)
    LOBBYWATCH_MCP_OTEL_ENABLED  0 | 1          (default: 0)
    LOBBYWATCH_MCP_OTEL_ENDPOINT URL of OTLP/HTTP collector (optional)

For HTTP/SSE deployments, optional CORS configuration via
``LOBBYWATCH_MCP_CORS_ORIGINS`` (comma-separated origin list, e.g.
``"https://app.example.ch,https://inspector.local"``). When set, a Starlette
``CORSMiddleware`` wraps the MCPServer ASGI app and exposes ``Mcp-Session-Id``
to browser clients (audit SDK-004). Without the env var no CORS headers are
emitted — the safe default.
"""

from __future__ import annotations

import logging
import os

from lobbywatch_mcp._observability import configure_logging, configure_tracing
from lobbywatch_mcp.server import build_server

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    raw = os.getenv("LOBBYWATCH_MCP_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _parse_allowed_hosts() -> list[str]:
    """Hostnames this server is reachable under (SEC-005).

    Needed once the bind is not loopback: the process cannot guess the service
    or public DNS name it is addressed by.
    """
    raw = os.getenv("LOBBYWATCH_MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return []
    return [h.strip() for h in raw.split(",") if h.strip()]


def build_transport_security(host: str, port: int):
    """Host/Origin allow-list for the HTTP transports (SEC-005, inbound half).

    Under mcp 2.x this is a per-app kwarg, and omitting it is *not* neutral: the
    SDK derives a default from the app's ``host`` argument and auto-enables
    ``127.0.0.1:*`` whenever that looks like loopback. Since ``host`` itself
    defaults to ``127.0.0.1``, a server started with
    ``LOBBYWATCH_MCP_HOST=0.0.0.0`` answered every request under a real hostname
    with HTTP 421. Before the migration to 2.x, ``host`` reached the ``FastMCP``
    constructor, where the same logic saw the real bind and left protection off.

    Returns ``None`` when no allow-list is derivable — a non-loopback bind with
    no ``LOBBYWATCH_MCP_ALLOWED_HOSTS``. A guessed list reproduces exactly that
    421, so the caller warns instead.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    loopback = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    allowed = _parse_allowed_hosts()
    if allowed:
        # Loopback stays reachable for container health checks and debugging.
        hosts = set(allowed) | loopback
    elif host in ("127.0.0.1", "localhost", "::1"):
        hosts = loopback | {f"{host}:{port}"}
    else:
        return None

    # Configured CORS origins must also pass the transport check, or the server
    # rejects exactly the browser clients CORS permits — a failure that only
    # shows up in a browser. "*" is not expressible (origins are compared
    # literally), so it is not copied across.
    origins = {o for o in _parse_cors_origins() if o != "*"}
    origins |= {f"http://{h}" for h in hosts}
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(hosts),
        allowed_origins=sorted(origins),
    )


def _run_asgi(transport: str, host: str, port: int) -> None:
    """Run the streamable-http or sse ASGI app under uvicorn, optionally
    wrapped with CORSMiddleware (audit SDK-004).
    """
    import uvicorn

    mcp = build_server()
    security = build_transport_security(host, port)
    if security is None:
        logger.warning(
            "DNS rebinding protection is OFF: the bind %s is not loopback and "
            "LOBBYWATCH_MCP_ALLOWED_HOSTS is empty. Set it to the hostnames this "
            "server is reachable under so Host and Origin are validated.",
            host,
        )
    # `host` must be the address uvicorn actually binds: the SDK derives its
    # allow-list from it, so leaving it at the default 421s a real deployment.
    if transport == "http":
        app = mcp.streamable_http_app(transport_security=security, host=host)
    else:
        app = mcp.sse_app(transport_security=security, host=host)

    cors_origins = _parse_cors_origins()
    if cors_origins:
        from starlette.middleware.cors import CORSMiddleware

        app = CORSMiddleware(
            app,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Mcp-Session-Id", "Authorization"],
            expose_headers=["Mcp-Session-Id"],
            allow_credentials=False,
            max_age=600,
        )
        logger.info("CORS enabled for origins: %s", cors_origins)

    uvicorn.run(app, host=host, port=port, log_config=None)


def main() -> None:
    configure_logging()
    configure_tracing()

    transport = os.getenv("LOBBYWATCH_MCP_TRANSPORT", "stdio").lower()

    if transport in ("http", "sse"):
        host = os.getenv("LOBBYWATCH_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("LOBBYWATCH_MCP_PORT", "8000"))
        _run_asgi(transport, host, port)
        return

    # Default: stdio. No HTTP surface, no CORS, no port binding.
    mcp = build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
