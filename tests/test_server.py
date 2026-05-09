"""Tests for the FastMCP server tool implementations.

These tests exercise the tool functions via the FastMCP registry to catch
schema / projection regressions.
"""

from __future__ import annotations

import pytest
from mcp.shared.exceptions import McpError

from lobbywatch_mcp.client import LobbywatchClient
from lobbywatch_mcp.server import _coerce_upstream, build_server


async def _call_tool(mcp, name: str, arguments: dict) -> dict:
    """Invoke a registered FastMCP tool and return its structured-content dict."""
    _content, structured = await mcp.call_tool(name, arguments)
    return structured


async def test_get_parlamentarier_by_name(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "lobbywatch_get_parlamentarier", {"name_or_id": "Mustermann"})
    assert payload["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"
    assert "Lobbywatch.ch" in payload["source"]  # attribution present


async def test_list_interessenbindungen_only_hauptberuflich(
    primed_client: LobbywatchClient,
) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp,
        "lobbywatch_list_interessenbindungen",
        {"name_or_id": "1", "nur_hauptberuflich": True},
    )
    assert payload["count"] == 1
    assert payload["interessenbindungen"][0]["hauptberuflich"] is True


async def test_search_nach_branche_bildung(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp, "lobbywatch_search_parlamentarier_nach_branche", {"branche_query": "Bildung"}
    )
    assert payload["count"] == 1
    assert payload["treffer"][0]["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"


async def test_search_with_kommission_filter(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp,
        "lobbywatch_search_parlamentarier_nach_branche",
        {"branche_query": "Finanz", "kommission": "WBK-N"},
    )
    assert payload["count"] == 0  # finance person is in FK-N, not WBK-N


async def test_ranking_by_ib_count(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "lobbywatch_get_ranking", {"limit": 5})
    assert payload["eintraege"][0]["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"
    assert payload["eintraege"][0]["wert"] == 2


async def test_ranking_rejects_invalid_criterion(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    # ValueError raised in the tool surfaces as a FastMCP ToolError.
    try:
        await _call_tool(mcp, "lobbywatch_get_ranking", {"kriterium": "bogus"})
    except Exception as exc:
        assert "kriterium" in str(exc).lower() or "bogus" in str(exc).lower()
        return
    raise AssertionError("Expected an error for invalid kriterium")


async def test_transparenzquote_wbk_n(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "lobbywatch_get_transparenzquote", {"kommission": "WBK-N"})
    assert payload["total"] == 2  # Anna + Claire
    assert payload["nach_bewertung"]["gut"] == 2


async def test_search_rejects_overlong_query(primed_client: LobbywatchClient) -> None:
    """SEC-018: branche_query is bound to <=200 chars."""
    mcp = build_server(client=primed_client)
    try:
        await _call_tool(
            mcp,
            "lobbywatch_search_parlamentarier_nach_branche",
            {"branche_query": "x" * 1000},
        )
    except Exception:
        return
    raise AssertionError("Expected an error for over-long branche_query")


async def test_ranking_rejects_overlimit(primed_client: LobbywatchClient) -> None:
    """SEC-018: limit is bound to 1..100 for ranking."""
    mcp = build_server(client=primed_client)
    try:
        await _call_tool(mcp, "lobbywatch_get_ranking", {"limit": 10_000})
    except Exception:
        return
    raise AssertionError("Expected an error for over-large limit")


async def test_tools_use_lobbywatch_namespace(primed_client: LobbywatchClient) -> None:
    """SEC-022: every registered tool name carries the lobbywatch_ prefix."""
    mcp = build_server(client=primed_client)
    tools = await mcp.list_tools()
    assert tools, "expected at least one tool"
    bad = [t.name for t in tools if not t.name.startswith("lobbywatch_")]
    assert not bad, f"unprefixed tools: {bad}"


async def test_coerce_upstream_passes_through_value() -> None:
    """OBS-001 helper: successful coroutines return their value unchanged."""

    async def ok() -> int:
        return 42

    assert await _coerce_upstream(ok()) == 42


async def test_coerce_upstream_converts_runtime_to_mcp_error() -> None:
    """OBS-001: RuntimeError from upstream surfaces as McpError, not raw."""

    async def boom() -> int:
        raise RuntimeError("upstream is down")

    with pytest.raises(McpError) as exc_info:
        await _coerce_upstream(boom())
    # The original exception is preserved as __cause__.
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert "upstream is down" in str(exc_info.value)


async def test_coerce_upstream_passes_through_mcp_error() -> None:
    """OBS-001: an already-typed McpError must not be double-wrapped."""
    from mcp.types import INVALID_PARAMS, ErrorData

    original = McpError(ErrorData(code=INVALID_PARAMS, message="bad arg"))

    async def already_typed() -> int:
        raise original

    with pytest.raises(McpError) as exc_info:
        await _coerce_upstream(already_typed())
    assert exc_info.value is original
