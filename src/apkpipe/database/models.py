"""SQLAlchemy ORM models for APKPipe."""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""
    pass


class WatchlistItem(Base):
    """Watchlist model representing apps monitored for release updates."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    package_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title_regex: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    min_version: Mapped[str] = mapped_column(String(64), nullable=False, default="0.0.0")
    releaser_whitelist: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    releaser_blacklist: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Apps")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    tasks: Mapped[List["DownloadTask"]] = relationship(
        "DownloadTask",
        back_populates="watchlist_item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class FeedSource(Base):
    """Feed source model representing RSS/ATOM feeds polled by the pipeline."""

    __tablename__ = "feed_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    feed_type: Mapped[str] = mapped_column(String(64), nullable=False, default="mobilism_rss")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DownloadTask(Base):
    """Download task model tracking pipeline processing state for matched releases."""

    __tablename__ = "download_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_item_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("watchlist_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feed_item_title: Mapped[str] = mapped_column(String(512), nullable=False)
    feed_item_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    matched_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    matched_releaser: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", index=True)
    mirror_urls: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    resolved_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    download_tier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    watchlist_item: Mapped[Optional["WatchlistItem"]] = relationship(
        "WatchlistItem",
        back_populates="tasks",
        lazy="selectin",
    )
    history: Mapped[Optional["DownloadHistory"]] = relationship(
        "DownloadHistory",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DownloadHistory(Base):
    """Historical audit log of completed or processed APK downloads."""

    __tablename__ = "download_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("download_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    releaser: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    target_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    download_tier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="completed", index=True)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Optional["DownloadTask"]] = relationship(
        "DownloadTask",
        back_populates="history",
        lazy="selectin",
    )


class AppSetting(Base):
    """Key-value application settings stored dynamically in the database."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
