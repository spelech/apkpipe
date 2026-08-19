"""Async SQLite database engine and session factory using SQLAlchemy and aiosqlite."""

from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from apkpipe.config import get_settings
from apkpipe.database.models import Base

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def normalize_db_url(url_or_path: str) -> str:
    """Normalize database URL or file path into an async sqlite URL."""
    if url_or_path.startswith("sqlite+aiosqlite://"):
        return url_or_path
    if url_or_path.startswith("sqlite://"):
        return url_or_path.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url_or_path == ":memory:":
        return "sqlite+aiosqlite:///:memory:"
    return f"sqlite+aiosqlite:///{url_or_path}"


def get_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """Get or create the async SQLAlchemy engine."""
    global _engine, _session_factory
    if db_url is not None or _engine is None:
        target_url = normalize_db_url(db_url or get_settings().database_url)
        
        engine_kwargs = {"echo": False}
        if ":memory:" in target_url:
            engine_kwargs["poolclass"] = StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        _engine = create_async_engine(target_url, **engine_kwargs)
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Get or create the async sessionmaker factory."""
    global _session_factory
    if engine is not None:
        return async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    if _session_factory is None:
        get_engine()
    return _session_factory  # type: ignore[return-value]


async def init_db(db_url: Optional[str] = None) -> AsyncEngine:
    """Initialize database tables for the given or default connection."""
    engine = get_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def close_db() -> None:
    """Dispose active engine connection pool and reset global references."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI and service async dependency yielding an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
