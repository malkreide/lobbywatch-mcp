"""lobbywatch-mcp — MCP server for the Lobbywatch.ch lobby database.

Part of the Swiss Public Data MCP Portfolio (https://github.com/malkreide).

Data © Lobbywatch.ch, licensed CC BY-SA 4.0.
Code licensed MIT.
"""

from lobbywatch_mcp._version import PACKAGE_VERSION

__version__ = PACKAGE_VERSION
__all__ = ["LobbywatchClient", "build_server"]

from lobbywatch_mcp.client import LobbywatchClient
from lobbywatch_mcp.server import build_server
