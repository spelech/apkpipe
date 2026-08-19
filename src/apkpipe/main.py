"""FastAPI Application Factory, Lifespan Handler, CORS, and Route Mounting."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    # Health Check Endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Health check endpoint returning system status and current timestamp."""
        return {
            "status": "healthy",
            "version": APP_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Root Endpoint
    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """Root API metadata."""
        return {
            "name": settings.app_name,
            "version": APP_VERSION,
            "status": "running",
            "docs_url": "/docs",
        }

    return app


# Default ASGI application instance for Uvicorn
app = create_app()
