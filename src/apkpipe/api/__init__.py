"""APKPipe REST API routers and route definitions."""

from apkpipe.api.routes_downloads import router as downloads_router
from apkpipe.api.routes_feeds import router as feeds_router
from apkpipe.api.routes_mcp import router as mcp_router
from apkpipe.api.routes_settings import router as settings_router
from apkpipe.api.routes_watchlist import router as watchlist_router

__all__ = [
    "watchlist_router",
    "feeds_router",
    "downloads_router",
    "settings_router",
    "mcp_router",
]
