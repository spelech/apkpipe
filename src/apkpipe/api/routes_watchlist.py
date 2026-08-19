"""FastAPI REST routes for Watchlist management."""

from datetime import datetime
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.database.db import get_db
from apkpipe.database.models import WatchlistItem, utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


class WatchlistItemCreate(BaseModel):
    """Schema for creating a new watchlist item."""

    app_name: str = Field(..., min_length=1, description="Application display name")
    package_name: Optional[str] = Field(None, description="Android package name (e.g. com.spotify.music)")
    title_regex: Optional[str] = Field(None, description="Regex pattern matching release titles")
    min_version: str = Field("0.0.0", description="Minimum acceptable version")
    releaser_whitelist: List[str] = Field(default_factory=list, description="Allowed releaser names")
    releaser_blacklist: List[str] = Field(default_factory=list, description="Blocked releaser names")
    enabled: bool = Field(True, description="Whether monitoring is active")
    category: str = Field("Apps", description="Category grouping for dashboard")

    @field_validator("title_regex")
    @classmethod
    def validate_regex(cls, v: Optional[str]) -> Optional[str]:
        """Ensure title_regex is a valid regular expression if provided."""
        if v is not None and v.strip():
            try:
                re.compile(v.strip())
            except re.error as exc:
                raise ValueError(f"Invalid regular expression '{v}': {exc}")
        return v


class WatchlistItemUpdate(BaseModel):
    """Schema for updating an existing watchlist item."""

    app_name: Optional[str] = None
    package_name: Optional[str] = None
    title_regex: Optional[str] = None
    min_version: Optional[str] = None
    releaser_whitelist: Optional[List[str]] = None
    releaser_blacklist: Optional[List[str]] = None
    enabled: Optional[bool] = None
    category: Optional[str] = None

    @field_validator("title_regex")
    @classmethod
    def validate_regex(cls, v: Optional[str]) -> Optional[str]:
        """Ensure title_regex is a valid regular expression if provided."""
        if v is not None and v.strip():
            try:
                re.compile(v.strip())
            except re.error as exc:
                raise ValueError(f"Invalid regular expression '{v}': {exc}")
        return v


class WatchlistItemResponse(BaseModel):
    """Schema for watchlist item serialization in responses."""

    id: int
    app_name: str
    package_name: Optional[str] = None
    title_regex: Optional[str] = None
    min_version: str
    releaser_whitelist: List[str]
    releaser_blacklist: List[str]
    enabled: bool
    category: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[WatchlistItemResponse])
async def list_watchlist(
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    query: Optional[str] = Query(None, description="Search term matching app name or package name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[WatchlistItem]:
    """Retrieve list of monitored watchlist applications with optional filtering."""
    stmt = select(WatchlistItem)

    if enabled is not None:
        stmt = stmt.where(WatchlistItem.enabled == enabled)

    if category is not None:
        stmt = stmt.where(WatchlistItem.category.ilike(f"%{category.strip()}%"))

    if query is not None and query.strip():
        q_term = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                WatchlistItem.app_name.ilike(q_term),
                WatchlistItem.package_name.ilike(q_term),
            )
        )

    stmt = stmt.order_by(WatchlistItem.app_name.asc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist_item(
    item_in: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItem:
    """Create a new watchlist monitoring entry."""
    item = WatchlistItem(
        app_name=item_in.app_name.strip(),
        package_name=item_in.package_name.strip() if item_in.package_name else None,
        title_regex=item_in.title_regex.strip() if item_in.title_regex else None,
        min_version=item_in.min_version.strip() if item_in.min_version else "0.0.0",
        releaser_whitelist=item_in.releaser_whitelist,
        releaser_blacklist=item_in.releaser_blacklist,
        enabled=item_in.enabled,
        category=item_in.category.strip() if item_in.category else "Apps",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("Created watchlist item '%s' (id=%d)", item.app_name, item.id)
    return item


@router.get("/{item_id}", response_model=WatchlistItemResponse)
async def get_watchlist_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItem:
    """Retrieve a single watchlist monitoring entry by ID."""
    stmt = select(WatchlistItem).where(WatchlistItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WatchlistItem {item_id} not found")
    return item


@router.put("/{item_id}", response_model=WatchlistItemResponse)
async def update_watchlist_item(
    item_id: int,
    item_in: WatchlistItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> WatchlistItem:
    """Update an existing watchlist monitoring entry."""
    stmt = select(WatchlistItem).where(WatchlistItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WatchlistItem {item_id} not found")

    update_data = item_in.model_dump(exclude_unset=True)
    for field_name, val in update_data.items():
        setattr(item, field_name, val)

    item.updated_at = utcnow()
    await db.commit()
    await db.refresh(item)
    logger.info("Updated watchlist item '%s' (id=%d)", item.app_name, item.id)
    return item


@router.delete("/{item_id}")
async def delete_watchlist_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete a watchlist monitoring entry."""
    stmt = select(WatchlistItem).where(WatchlistItem.id == item_id)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WatchlistItem {item_id} not found")

    app_name = item.app_name
    await db.delete(item)
    await db.commit()
    logger.info("Deleted watchlist item '%s' (id=%d)", app_name, item_id)
    return {"status": "deleted", "id": item_id, "app_name": app_name}
