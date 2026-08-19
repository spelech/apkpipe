"""FastAPI Application Factory, Lifespan Handler, CORS, and Route Mounting."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apkpipe.api import (
    downloads_router,
    feeds_router,
    mcp_router,
    settings_router,
    watchlist_router,
)
from apkpipe.config import get_settings
from apkpipe.database.db import close_db, init_db
from apkpipe.feeds.poller import FeedPoller

logger = logging.getLogger("apkpipe")

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager: initializes database and poller lifecycle."""
    logger.info("Starting APKPipe FastAPI Application (version %s)...", APP_VERSION)

    # 1. Initialize SQLite schema tables
    await init_db()

    # 2. Instantiate and start background feed poller service
    poller = FeedPoller()
    app.state.poller = poller
    await poller.start()

    yield

    # 3. Shutdown cleanup
    logger.info("Shutting down APKPipe FastAPI Application...")
    if hasattr(app.state, "poller") and app.state.poller is not None:
        await app.state.poller.stop()

    await close_db()
    logger.info("APKPipe shutdown complete.")


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance with routes and middleware."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Automated APK & RSS media pipeline with Real-Debrid, JDownloader fallback, Nextcloud ingestion, Web UI, and MCP server.",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    # CORS Middleware configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount REST API Routers under /api
    app.include_router(watchlist_router, prefix="/api")
    app.include_router(feeds_router, prefix="/api")
    app.include_router(downloads_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")

    # Mount MCP Protocol Router (/mcp, /mcp/sse, /mcp/messages)
    app.include_router(mcp_router)

    # Web UI Template & Static File Setup
    web_dir = Path(__file__).resolve().parent / "web"
    templates_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    templates = Jinja2Templates(directory=str(templates_dir))

    # Health Check Endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Health check endpoint returning system status and current timestamp."""
        return {
            "status": "healthy",
            "version": APP_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Web UI Dashboard and Page Routes
    @app.get("/", response_class=HTMLResponse, tags=["Web UI"])
    async def dashboard_page(request: Request) -> HTMLResponse:
        """Web UI Dashboard overview page."""
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"active_page": "dashboard", "app_name": settings.app_name, "version": APP_VERSION},
        )

    @app.get("/watchlist", response_class=HTMLResponse, tags=["Web UI"])
    async def watchlist_page(request: Request) -> HTMLResponse:
        """Web UI Watchlist management page."""
        return templates.TemplateResponse(
            request=request,
            name="watchlist.html",
            context={"active_page": "watchlist", "app_name": settings.app_name, "version": APP_VERSION},
        )

    @app.get("/feeds", response_class=HTMLResponse, tags=["Web UI"])
    async def feeds_page(request: Request) -> HTMLResponse:
        """Web UI Feed sources management page."""
        return templates.TemplateResponse(
            request=request,
            name="feeds.html",
            context={"active_page": "feeds", "app_name": settings.app_name, "version": APP_VERSION},
        )

    @app.get("/history", response_class=HTMLResponse, tags=["Web UI"])
    async def history_page(request: Request) -> HTMLResponse:
        """Web UI Download queue and audit history page."""
        return templates.TemplateResponse(
            request=request,
            name="history.html",
            context={"active_page": "history", "app_name": settings.app_name, "version": APP_VERSION},
        )

    @app.get("/settings", response_class=HTMLResponse, tags=["Web UI"])
    async def settings_page(request: Request) -> HTMLResponse:
        """Web UI Configuration settings page."""
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={"active_page": "settings", "app_name": settings.app_name, "version": APP_VERSION},
        )

    return app


# Default ASGI application instance for Uvicorn
app = create_app()
