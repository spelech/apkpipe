"""FastAPI REST routes for application configuration and runtime settings."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.config import get_settings
from apkpipe.database.db import get_db
from apkpipe.database.models import AppSetting, utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


class SettingsUpdateRequest(BaseModel):
    """Schema for updating application runtime settings."""

    app_name: Optional[str] = None
    debug: Optional[bool] = None
    download_dir: Optional[str] = None
    staging_dir: Optional[str] = None
    poll_interval_seconds: Optional[int] = None
    real_debrid_api_token: Optional[str] = None
    jdownloader_email: Optional[str] = None
    jdownloader_password: Optional[str] = None
    jdownloader_device_name: Optional[str] = None
    jdownloader_watch_dir: Optional[str] = None
    scraper_url: Optional[str] = None
    nextcloud_url: Optional[str] = None
    nextcloud_token: Optional[str] = None
    nextcloud_occ_command: Optional[str] = None
    apprise_url: Optional[str] = None
    ntfy_topic: Optional[str] = None

    model_config = ConfigDict(extra="allow")


async def _get_merged_settings(db: AsyncSession) -> Dict[str, Any]:
    """Merge environment settings with database AppSetting records."""
    base_settings = get_settings().model_dump()
    
    # Query database settings
    stmt = select(AppSetting)
    db_settings = (await db.execute(stmt)).scalars().all()
    db_map = {item.key: item.value for item in db_settings}

    merged = dict(base_settings)
    for key, val in db_map.items():
        if key in merged:
            # Cast type to match base setting type
            orig_val = merged[key]
            if isinstance(orig_val, bool):
                merged[key] = val.lower() in ("true", "1", "yes")
            elif isinstance(orig_val, int):
                try:
                    merged[key] = int(val)
                except ValueError:
                    merged[key] = val
            elif isinstance(orig_val, float):
                try:
                    merged[key] = float(val)
                except ValueError:
                    merged[key] = val
            else:
                merged[key] = val
        else:
            merged[key] = val

    return merged


@router.get("")
async def get_settings_endpoint(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve current application configuration and dynamic settings."""
    return await _get_merged_settings(db)


@router.post("")
async def update_settings_endpoint(
    settings_in: SettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Save or update runtime application settings in the database."""
    update_data = settings_in.model_dump(exclude_unset=True)

    for key, val in update_data.items():
        if val is None:
            continue
        str_val = str(val) if not isinstance(val, bool) else ("true" if val else "false")
        
        stmt = select(AppSetting).where(AppSetting.key == key)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.value = str_val
            existing.updated_at = utcnow()
        else:
            setting_obj = AppSetting(key=key, value=str_val)
            db.add(setting_obj)

    await db.commit()
    logger.info("Updated %d settings keys in database", len(update_data))
    return await _get_merged_settings(db)
