"""Model Context Protocol (MCP 2024-11-05) Server and Tool Registry for APKPipe."""

from apkpipe.mcp.server import McpServer
from apkpipe.mcp.tools import (
    ALL_TOOLS,
    TOOL_REGISTRY,
    add_to_watchlist_tool,
    download_url_tool,
    execute_tool,
    get_history_tool,
    get_system_status_tool,
    list_watchlist_tool,
    remove_from_watchlist_tool,
    search_feed_tool,
    trigger_poll_tool,
)

__all__ = [
    "McpServer",
    "ALL_TOOLS",
    "TOOL_REGISTRY",
    "execute_tool",
    "list_watchlist_tool",
    "add_to_watchlist_tool",
    "remove_from_watchlist_tool",
    "search_feed_tool",
    "trigger_poll_tool",
    "download_url_tool",
    "get_history_tool",
    "get_system_status_tool",
]
