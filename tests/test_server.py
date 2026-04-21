"""Tests for the FastMCP server tool implementations.

These tests exercise the tool functions via the FastMCP registry to catch
schema / projection regressions.
"""

from __future__ import annotations

from lobbywatch_mcp.client import LobbywatchClient
from lobbywatch_mcp.server import build_server


async def _call_tool(mcp, name: str, arguments: dict) -> dict:
    """Invoke a registered FastMCP tool and return its structured-content dict."""
    _content, structured = await mcp.call_tool(name, arguments)
    return structured


async def test_get_parlamentarier_by_name(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "get_parlamentarier", {"name_or_id": "Mustermann"})
    assert payload["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"
    assert "Lobbywatch.ch" in payload["source"]  # attribution present


async def test_list_interessenbindungen_only_hauptberuflich(
    primed_client: LobbywatchClient,
) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp,
        "list_interessenbindungen",
        {"name_or_id": "1", "nur_hauptberuflich": True},
    )
    assert payload["count"] == 1
    assert payload["interessenbindungen"][0]["hauptberuflich"] is True


async def test_search_nach_branche_bildung(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp, "search_parlamentarier_nach_branche", {"branche_query": "Bildung"}
    )
    assert payload["count"] == 1
    assert payload["treffer"][0]["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"


async def test_search_with_kommission_filter(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(
        mcp,
        "search_parlamentarier_nach_branche",
        {"branche_query": "Finanz", "kommission": "WBK-N"},
    )
    assert payload["count"] == 0  # finance person is in FK-N, not WBK-N


async def test_ranking_by_ib_count(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "get_ranking", {"limit": 5})
    assert payload["eintraege"][0]["parlamentarier"]["anzeige_name"] == "Mustermann, Anna"
    assert payload["eintraege"][0]["wert"] == 2


async def test_ranking_rejects_invalid_criterion(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    # ValueError raised in the tool surfaces as a FastMCP ToolError.
    try:
        await _call_tool(mcp, "get_ranking", {"kriterium": "bogus"})
    except Exception as exc:
        assert "kriterium" in str(exc).lower() or "bogus" in str(exc).lower()
        return
    raise AssertionError("Expected an error for invalid kriterium")


async def test_transparenzquote_wbk_n(primed_client: LobbywatchClient) -> None:
    mcp = build_server(client=primed_client)
    payload = await _call_tool(mcp, "get_transparenzquote", {"kommission": "WBK-N"})
    assert payload["total"] == 2  # Anna + Claire
    assert payload["nach_bewertung"]["gut"] == 2
