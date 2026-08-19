"""FastAPI REST routes for Feed sources and immediate polling triggers."""

from datetime import datetime
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.database.db import get_db
from apkpipe.database.models import FeedSource
from apkpipe.feeds.poller import FeedPoller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feeds", tags=["Feeds"])


class FeedSourceCreate(BaseModel):
    """Schema for creating a new feed source."""

    name: str = Field(..., min_length=1, description="Feed display title")
    url: str = Field(..., min_length=1, description="RSS or Atom feed URL / endpoint")
    feed_type: str = Field("mobilism_rss", description="Parser handler type")
    enabled: bool = Field(True, description="Whether automated polling is active")
    poll_interval_minutes: int = Field(15, ge=1, description="Poll frequency in minutes")


class FeedSourceUpdate(BaseModel):
    """Schema for updating an existing feed source."""

    name: Optional[str] = None
    url: Optional[str] = None
    feed_type: Optional[str] = None
    enabled: Optional[bool] = None
    poll_interval_minutes: Optional[int] = None


class FeedSourceResponse(BaseModel):
    """Schema for serializing feed sources in REST responses."""

    id: int
    name: str
    url: str
    feed_type: str
    enabled: bool
    poll_interval_minutes: int
    last_polled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


def _get_poller(request: Request) -> FeedPoller:
    """Retrieve active FeedPoller instance from application state or create fallback."""
    if hasattr(request.app.state, "poller") and request.app.state.poller is not None:
        return request.app.state.poller
    return FeedPoller()


@router.get("", response_model=List[FeedSourceResponse])
async def list_feeds(
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    db: AsyncSession = Depends(get_db),
) -> List[FeedSource]:
    """List all configured RSS and Atom feed sources."""
    stmt = select(FeedSource)
    if enabled is not None:
        stmt = stmt.where(FeedSource.enabled == enabled)
    stmt = stmt.order_by(FeedSource.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=FeedSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_feed(
    feed_in: FeedSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> FeedSource:
    """Register a new feed source for background polling."""
    # Check if URL already registered
    stmt = select(FeedSource).where(FeedSource.url == feed_in.url.strip())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feed URL already registered with ID {existing.id}",
        )

    feed = FeedSource(
        name=feed_in.name.strip(),
        url=feed_in.url.strip(),
        feed_type=feed_in.feed_type.strip(),
        enabled=feed_in.enabled,
        poll_interval_minutes=feed_in.poll_interval_minutes,
    )
    db.add(feed)
    await db.commit()
    await db.refresh(feed)
    logger.info("Registered new feed source '%s' (id=%d)", feed.name, feed.id)
    return feed


@router.get("/{feed_id}", response_model=FeedSourceResponse)
async def get_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
) -> FeedSource:
    """Retrieve details for a single feed source by ID."""
    stmt = select(FeedSource).where(FeedSource.id == feed_id)
    feed = (await db.execute(stmt)).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"FeedSource {feed_id} not found")
    return feed


@router.put("/{feed_id}", response_model=FeedSourceResponse)
async def update_feed(
    feed_id: int,
    feed_in: FeedSourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> FeedSource:
    """Update configuration for an existing feed source."""
    stmt = select(FeedSource).where(FeedSource.id == feed_id)
    feed = (await db.execute(stmt)).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"FeedSource {feed_id} not found")

    update_data = feed_in.model_dump(exclude_unset=True)
    for field_name, val in update_data.items():
        setattr(feed, field_name, val)

    await db.commit()
    await db.refresh(feed)
    logger.info("Updated feed source '%s' (id=%d)", feed.name, feed.id)
    return feed


@router.delete("/{feed_id}")
async def delete_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a feed source."""
    stmt = select(FeedSource).where(FeedSource.id == feed_id)
    feed = (await db.execute(stmt)).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"FeedSource {feed_id} not found")

    feed_name = feed.name
    await db.delete(feed)
    await db.commit()
    logger.info("Deleted feed source '%s' (id=%d)", feed_name, feed_id)
    return {"status": "deleted", "id": feed_id, "name": feed_name}


@router.post("/{feed_id}/poll")
async def trigger_single_feed_poll(
    feed_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Immediately poll and process releases from a specific feed."""
    stmt = select(FeedSource).where(FeedSource.id == feed_id)
    feed = (await db.execute(stmt)).scalar_one_or_none()
    if feed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"FeedSource {feed_id} not found")

    poller = _get_poller(request)
    return await poller.poll_single_feed(feed_id)


@router.post("/poll-all")
async def trigger_all_feeds_poll(
    request: Request,
) -> dict:
    """Immediately poll and process releases from all enabled feeds."""
    poller = _get_poller(request)
    return await poller.poll_all_feeds()
