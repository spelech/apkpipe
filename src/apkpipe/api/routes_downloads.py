"""FastAPI REST routes for Download Queue, History, and Manual Triggers."""

from datetime import datetime
import logging
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.config import get_settings
from apkpipe.database.db import get_db, get_session_factory
from apkpipe.database.models import DownloadHistory, DownloadTask, utcnow
from apkpipe.downloader.archive import ArchiveExtractor
from apkpipe.downloader.engine import DownloadEngine
from apkpipe.downloader.organizer import FileOrganizer
from apkpipe.extractors.mobilism import MobilismExtractor
from apkpipe.extractors.scraper_client import PlaywrightScraperClient
from apkpipe.feeds.parser import extract_title_metadata
from apkpipe.integrations.nextcloud import NextcloudClient
from apkpipe.notifications.apprise import NotificationService
from apkpipe.resolvers.manager import ResolutionManager
from apkpipe.resolvers.real_debrid import RealDebridResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/downloads", tags=["Downloads"])


def _get_writable_dir(preferred_path: Optional[str], default_name: str) -> Path:
    """Return configured directory if writable/creatable, otherwise safe temp dir fallback."""
    if preferred_path:
        p = Path(preferred_path)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except (PermissionError, OSError):
            pass
    fallback = Path(tempfile.gettempdir()) / default_name
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


class DownloadTaskResponse(BaseModel):
    """Schema for serializing DownloadTask records in responses."""

    id: int
    watchlist_item_id: Optional[int] = None
    feed_item_title: str
    feed_item_url: Optional[str] = None
    matched_version: Optional[str] = None
    matched_releaser: Optional[str] = None
    status: str
    mirror_urls: List[str] = []
    resolved_url: Optional[str] = None
    download_tier: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DownloadHistoryResponse(BaseModel):
    """Schema for serializing DownloadHistory audit records."""

    id: int
    task_id: Optional[int] = None
    app_name: str
    version: Optional[str] = None
    releaser: Optional[str] = None
    target_path: Optional[str] = None
    file_size: Optional[int] = None
    duration_seconds: Optional[float] = None
    download_tier: Optional[str] = None
    status: str
    downloaded_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ManualDownloadRequest(BaseModel):
    """Schema for manually submitting a URL or release topic for download."""

    url: str = Field(..., min_length=1, description="Direct download URL or forum release topic URL")
    app_name: Optional[str] = Field(None, description="App name override")
    version: Optional[str] = Field(None, description="App version tag override")
    releaser: Optional[str] = Field(None, description="Releaser name override")
    category: Optional[str] = Field("Apps", description="Category folder")
    auto_resolve: bool = Field(True, description="Immediately resolve and download")
    trigger_ingest: bool = Field(True, description="Trigger Nextcloud scan and notifications")
    download_tier: Optional[str] = Field(None, description="Preferred resolver tier")


@router.get("/queue", response_model=List[DownloadTaskResponse])
async def list_download_queue(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by task status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[DownloadTask]:
    """List active, pending, or filtered download tasks in the processing queue."""
    stmt = select(DownloadTask)
    if status_filter:
        stmt = stmt.where(DownloadTask.status == status_filter)
    stmt = stmt.order_by(DownloadTask.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/history", response_model=List[DownloadHistoryResponse])
async def list_download_history(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by history status"),
    query: Optional[str] = Query(None, description="Search app name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> List[DownloadHistory]:
    """Retrieve historical audit logs of downloaded APK releases."""
    stmt = select(DownloadHistory)
    if status_filter:
        stmt = stmt.where(DownloadHistory.status == status_filter)
    if query and query.strip():
        stmt = stmt.where(DownloadHistory.app_name.ilike(f"%{query.strip()}%"))
    stmt = stmt.order_by(DownloadHistory.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/manual", response_model=DownloadTaskResponse, status_code=status.HTTP_201_CREATED)
async def manual_download(
    req: ManualDownloadRequest,
    db: AsyncSession = Depends(get_db),
) -> DownloadTask:
    """Manually submit a download URL or topic for resolution and ingestion."""
    url = req.url.strip()
    app_name = req.app_name.strip() if req.app_name else None
    version = req.version.strip() if req.version else None
    releaser = req.releaser.strip() if req.releaser else None

    if not app_name:
        meta = extract_title_metadata(url)
        app_name = meta.app_name or Path(urllib.parse.urlparse(url).path).stem or "ManualDownload"
        if not version:
            version = meta.version
        if not releaser:
            releaser = meta.releaser

    task = DownloadTask(
        feed_item_title=app_name,
        feed_item_url=url,
        matched_version=version,
        matched_releaser=releaser,
        status="pending",
        mirror_urls=[url],
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    if not req.auto_resolve:
        return task

    # Perform immediate resolution and download
    settings = get_settings()
    staging_dir = _get_writable_dir(settings.staging_dir, "apkpipe_staging")
    download_dir = _get_writable_dir(settings.download_dir, "apkpipe_downloads")

    rd_resolver = (
        RealDebridResolver(api_token=settings.real_debrid_api_token)
        if settings.real_debrid_api_token
        else None
    )
    resolver_mgr = ResolutionManager(rd_resolver=rd_resolver)
    downloader = DownloadEngine(staging_dir=staging_dir)
    organizer = FileOrganizer(base_download_dir=download_dir)
    archive_ext = ArchiveExtractor()
    nextcloud = NextcloudClient()
    notifier = NotificationService()
    scraper_client = PlaywrightScraperClient(base_url=settings.scraper_url)
    mobilism_extractor = MobilismExtractor(scraper_client=scraper_client)

    start_time = time.monotonic()
    try:
        # Extract mirrors if URL is a topic
        candidate_links = [url]
        if url.startswith("http://") or url.startswith("https://"):
            try:
                extracted = await mobilism_extractor.fetch_and_extract(url)
                extracted_urls = [e.url for e in extracted if e.url]
                if extracted_urls:
                    candidate_links = extracted_urls
            except Exception as exc:
                logger.debug("Extraction failed for %s: %s", url, exc)

        task.mirror_urls = candidate_links
        task.status = "resolving"
        await db.commit()

        resolved = await resolver_mgr.resolve(candidate_links, preferred_tier=req.download_tier)
        if not resolved:
            raise Exception("Failed to resolve candidate download link")

        task.resolved_url = resolved.download_url
        task.download_tier = getattr(resolved, "tier", None)
        task.status = "downloading"
        await db.commit()

        downloaded_file = await downloader.download(
            url_or_resolved=resolved,
            destination=staging_dir,
        )

        if archive_ext.is_archive(downloaded_file):
            extracted_apks = archive_ext.extract(
                archive_or_apk_path=downloaded_file,
                destination_dir=staging_dir,
                flatten=True,
            )
            primary_apk = extracted_apks[0]
        else:
            primary_apk = downloaded_file

        organized = organizer.organize(
            source_file=primary_apk,
            app_name=app_name,
            version=version,
            releaser=releaser,
        )

        elapsed = time.monotonic() - start_time
        task.file_path = str(organized.destination_path)
        task.file_size = organized.filesize
        task.status = "completed"
        task.completed_at = utcnow()

        if req.trigger_ingest:
            history = DownloadHistory(
                task_id=task.id,
                app_name=app_name,
                version=version,
                releaser=releaser,
                target_path=str(organized.destination_path),
                file_size=organized.filesize,
                duration_seconds=elapsed,
                download_tier=task.download_tier,
                status="completed",
            )
            db.add(history)
            await db.commit()

            await nextcloud.trigger_occ_scan(path=organized.destination_path)
            await notifier.notify_download_completed(
                app_name=app_name,
                version=version,
                releaser=releaser,
                target_path=str(organized.destination_path),
                file_size=organized.filesize,
                download_tier=task.download_tier,
            )

        await db.commit()
        await db.refresh(task)
        return task

    except Exception as exc:
        logger.exception("Manual download failed for %s: %s", url, exc)
        task.status = "failed"
        task.error_message = str(exc)
        task.completed_at = utcnow()
        await db.commit()
        await db.refresh(task)
        return task


@router.post("/{task_id}/retry", response_model=DownloadTaskResponse)
async def retry_download_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
) -> DownloadTask:
    """Retry a failed or pending download task."""
    stmt = select(DownloadTask).where(DownloadTask.id == task_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DownloadTask {task_id} not found")

    # Reset task state
    task.status = "pending"
    task.error_message = None
    task.completed_at = None
    await db.commit()
    await db.refresh(task)

    # Re-run resolution & download
    settings = get_settings()
    staging_dir = _get_writable_dir(settings.staging_dir, "apkpipe_staging")
    download_dir = _get_writable_dir(settings.download_dir, "apkpipe_downloads")

    rd_resolver = (
        RealDebridResolver(api_token=settings.real_debrid_api_token)
        if settings.real_debrid_api_token
        else None
    )
    resolver_mgr = ResolutionManager(rd_resolver=rd_resolver)
    downloader = DownloadEngine(staging_dir=staging_dir)
    organizer = FileOrganizer(base_download_dir=download_dir)
    archive_ext = ArchiveExtractor()
    nextcloud = NextcloudClient()
    notifier = NotificationService()

    app_name = task.feed_item_title
    version = task.matched_version
    releaser = task.matched_releaser
    candidate_links = task.mirror_urls or ([task.feed_item_url] if task.feed_item_url else [])

    start_time = time.monotonic()
    try:
        task.status = "resolving"
        await db.commit()

        resolved = await resolver_mgr.resolve(candidate_links)
        if not resolved:
            raise Exception("Failed to resolve download link on retry")

        task.resolved_url = resolved.download_url
        task.download_tier = getattr(resolved, "tier", None)
        task.status = "downloading"
        await db.commit()

        downloaded_file = await downloader.download(
            url_or_resolved=resolved,
            destination=staging_dir,
        )

        if archive_ext.is_archive(downloaded_file):
            extracted_apks = archive_ext.extract(
                archive_or_apk_path=downloaded_file,
                destination_dir=staging_dir,
                flatten=True,
            )
            primary_apk = extracted_apks[0]
        else:
            primary_apk = downloaded_file

        organized = organizer.organize(
            source_file=primary_apk,
            app_name=app_name,
            version=version,
            releaser=releaser,
        )

        elapsed = time.monotonic() - start_time
        task.file_path = str(organized.destination_path)
        task.file_size = organized.filesize
        task.status = "completed"
        task.completed_at = utcnow()

        history = DownloadHistory(
            task_id=task.id,
            app_name=app_name,
            version=version,
            releaser=releaser,
            target_path=str(organized.destination_path),
            file_size=organized.filesize,
            duration_seconds=elapsed,
            download_tier=task.download_tier,
            status="completed",
        )
        db.add(history)
        await db.commit()

        await nextcloud.trigger_occ_scan(path=organized.destination_path)
        await notifier.notify_download_completed(
            app_name=app_name,
            version=version,
            releaser=releaser,
            target_path=str(organized.destination_path),
            file_size=organized.filesize,
            download_tier=task.download_tier,
        )

        await db.refresh(task)
        return task

    except Exception as exc:
        logger.warning("Retry failed for task %d: %s", task.id, exc)
        task.status = "failed"
        task.error_message = str(exc)
        task.completed_at = utcnow()
        await db.commit()
        await db.refresh(task)
        return task


@router.delete("/{task_id}")
async def delete_download_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel or delete a download task by ID."""
    stmt = select(DownloadTask).where(DownloadTask.id == task_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"DownloadTask {task_id} not found")

    title = task.feed_item_title
    await db.delete(task)
    await db.commit()
    logger.info("Deleted download task %d (%s)", task_id, title)
    return {"status": "deleted", "id": task_id, "title": title}
