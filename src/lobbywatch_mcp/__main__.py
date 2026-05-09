"""CLI entry point for lobbywatch-mcp.

Transport selection follows the Swiss Public Data MCP Portfolio convention:
set the env var ``LOBBYWATCH_MCP_TRANSPORT`` to ``stdio`` (default) or ``http``.
"""

from __future__ import annotations

import os

from lobbywatch_mcp.server import build_server


def main() -> None:
    transport = os.getenv("LOBBYWATCH_MCP_TRANSPORT", "stdio").lower()
    mcp = build_server()

    if transport == "http":
        host = os.getenv("LOBBYWATCH_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("LOBBYWATCH_MCP_PORT", "8000"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    elif transport == "sse":
        host = os.getenv("LOBBYWATCH_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("LOBBYWATCH_MCP_PORT", "8000"))
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
