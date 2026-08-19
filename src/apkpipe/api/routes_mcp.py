"""Model Context Protocol (MCP 2026-07-28 RC) FastAPI Router Integration."""

from apkpipe.mcp.server import McpServer

# Default global MCP server instance
mcp_server = McpServer()
router = mcp_server.get_router()

__all__ = ["router", "mcp_server"]
