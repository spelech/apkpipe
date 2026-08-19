"""Background feed polling service, watchlist matcher, and automated download pipeline."""

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence, Union
import urllib.parse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apkpipe.config import get_settings
from apkpipe.database.db import get_session_factory
from apkpipe.database.models import (
    AppSetting,
    DownloadHistory,
    DownloadTask,
    FeedSource,
    WatchlistItem,
    utcnow,
)
from apkpipe.downloader.archive import ArchiveExtractor
from apkpipe.downloader.engine import DownloadEngine
from apkpipe.downloader.organizer import FileOrganizer, OrganizedFile
from apkpipe.extractors.mobilism import MobilismExtractor
from apkpipe.extractors.scraper_client import PlaywrightScraperClient
from apkpipe.feeds.matcher import MatchResult, match_feed_item
from apkpipe.feeds.parser import CandidateMetadata, FeedItem, extract_title_metadata, parse_feed
from apkpipe.integrations.nextcloud import NextcloudClient
from apkpipe.notifications.apprise import (
    NotificationEvent,
    NotificationSeverity,
    NotificationService,
)
from apkpipe.resolvers.manager import ResolutionManager, ResolverManager
from apkpipe.resolvers.real_debrid import RealDebridResolver

logger = logging.getLogger(__name__)


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


class FeedPoller:
    """Background service coordinating RSS polling, watchlist matching, link resolution, and ingest."""

    def __init__(
        self,
        poll_interval_seconds: Optional[int] = None,
        session_factory: Any = None,
        resolver_manager: Optional[ResolutionManager] = None,
        download_engine: Optional[DownloadEngine] = None,
        archive_extractor: Optional[ArchiveExtractor] = None,
        file_organizer: Optional[FileOrganizer] = None,
        nextcloud_client: Optional[NextcloudClient] = None,
        notification_service: Optional[NotificationService] = None,
        mobilism_extractor: Optional[MobilismExtractor] = None,
    ) -> None:
        """Initialize FeedPoller with dependencies or defaults."""
        settings = get_settings()
        self.poll_interval_seconds = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else settings.poll_interval_seconds
        )
        self.session_factory = session_factory or get_session_factory()

        self.staging_dir = _get_writable_dir(settings.staging_dir, "apkpipe_staging")
        self.download_dir = _get_writable_dir(settings.download_dir, "apkpipe_downloads")

        rd_resolver = (
            RealDebridResolver(api_token=settings.real_debrid_api_token)
            if settings.real_debrid_api_token
            else None
        )
        self.resolver_manager = (
            resolver_manager if resolver_manager is not None else ResolutionManager(rd_resolver=rd_resolver)
        )
        self.download_engine = (
            download_engine
            if download_engine is not None
            else DownloadEngine(staging_dir=self.staging_dir)
        )
        self.archive_extractor = (
            archive_extractor if archive_extractor is not None else ArchiveExtractor()
        )
        self.file_organizer = (
            file_organizer
            if file_organizer is not None
            else FileOrganizer(base_download_dir=self.download_dir)
        )
        self.nextcloud_client = (
            nextcloud_client if nextcloud_client is not None else NextcloudClient()
        )
        self.notification_service = (
            notification_service if notification_service is not None else NotificationService()
        )
        scraper_client = PlaywrightScraperClient(base_url=settings.scraper_url)
        self.mobilism_extractor = (
            mobilism_extractor
            if mobilism_extractor is not None
            else MobilismExtractor(scraper_client=scraper_client)
        )

        self._is_running: bool = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        """Return True if the background polling loop is active."""
        return self._is_running

    async def start(self) -> None:
        """Start the background feed polling loop."""
        if self._is_running:
            logger.info("FeedPoller is already running.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "FeedPoller background service started (interval: %ds).", self.poll_interval_seconds
        )

    async def stop(self) -> None:
        """Gracefully stop the background polling task."""
        if not self._is_running and self._task is None:
            return

        self._is_running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug("Error while stopping poller task: %s", exc)
            self._task = None

        logger.info("FeedPoller background service stopped.")

    async def _run_loop(self) -> None:
        """Main periodic polling loop."""
        while self._is_running:
            try:
                await self.poll_all_feeds()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error during feed polling cycle: %s", exc)

            try:
                await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                break

    async def _fetch_feed_content(self, url_or_xml: str) -> str:
        """Fetch feed XML text from URL or return string if inline XML."""
        if url_or_xml.startswith("http://") or url_or_xml.startswith("https://"):
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url_or_xml)
                resp.raise_for_status()
                return resp.text
        return url_or_xml

    async def poll_all_feeds(self) -> Dict[str, Any]:
        """Poll all enabled feed sources in the database and process releases."""
        async with self.session_factory() as session:
            feed_stmt = select(FeedSource).where(FeedSource.enabled.is_(True))
            feed_sources = (await session.execute(feed_stmt)).scalars().all()

            wl_stmt = select(WatchlistItem).where(WatchlistItem.enabled.is_(True))
            watchlist_items = (await session.execute(wl_stmt)).scalars().all()

            total_checked = 0
            total_matches = 0
            total_created = 0
            total_completed = 0
            errors: List[Dict[str, Any]] = []

            for source in feed_sources:
                try:
                    feed_content = await self._fetch_feed_content(source.url)
                    items = parse_feed(feed_content)
                    total_checked += len(items)

                    for item in items:
                        task = await self.process_item(item, watchlist_items, session=session)
                        if task is not None:
                            total_matches += 1
                            total_created += 1
                            if task.status == "completed":
                                total_completed += 1

                    source.last_polled_at = utcnow()
                    await session.commit()
                except Exception as exc:
                    logger.warning("Failed to poll feed %s (id=%d): %s", source.name, source.id, exc)
                    errors.append({"feed_id": source.id, "name": source.name, "error": str(exc)})

            return {
                "status": "ok" if not errors else "partial",
                "polled_feeds": len(feed_sources),
                "items_checked": total_checked,
                "matches_found": total_matches,
                "tasks_created": total_created,
                "tasks_completed": total_completed,
                "errors": errors,
            }

    async def poll_single_feed(self, feed_id: int) -> Dict[str, Any]:
        """Poll a single feed source by its database ID."""
        async with self.session_factory() as session:
            feed_stmt = select(FeedSource).where(FeedSource.id == feed_id)
            source = (await session.execute(feed_stmt)).scalar_one_or_none()
            if source is None:
                return {
                    "status": "error",
                    "message": f"FeedSource {feed_id} not found",
                    "polled_feeds": 0,
                    "items_checked": 0,
                    "matches_found": 0,
                    "tasks_created": 0,
                    "tasks_completed": 0,
                }

            wl_stmt = select(WatchlistItem).where(WatchlistItem.enabled.is_(True))
            watchlist_items = (await session.execute(wl_stmt)).scalars().all()

            total_checked = 0
            matches_found = 0
            tasks_created = 0
            tasks_completed = 0
            error_msg: Optional[str] = None

            try:
                feed_content = await self._fetch_feed_content(source.url)
                items = parse_feed(feed_content)
                total_checked = len(items)

                for item in items:
                    task = await self.process_item(item, watchlist_items, session=session)
                    if task is not None:
                        matches_found += 1
                        tasks_created += 1
                        if task.status == "completed":
                            tasks_completed += 1

                source.last_polled_at = utcnow()
                await session.commit()
            except Exception as exc:
                logger.warning("Error polling feed %d: %s", feed_id, exc)
                error_msg = str(exc)

            return {
                "status": "ok" if not error_msg else "error",
                "polled_feeds": 1,
                "items_checked": total_checked,
                "matches_found": matches_found,
                "tasks_created": tasks_created,
                "tasks_completed": tasks_completed,
                "error": error_msg,
            }

    async def process_item(
        self,
        feed_item: FeedItem,
        watchlist_items: Sequence[WatchlistItem],
        session: Optional[AsyncSession] = None,
    ) -> Optional[DownloadTask]:
        """Evaluate a feed item against watchlist rules and execute pipeline if matched."""
        match_res = match_feed_item(feed_item, watchlist_items)
        if not match_res or not match_res.matched:
            return None

        async def _run_process(s: AsyncSession) -> Optional[DownloadTask]:
            # 1. Deduplication check: check if task exists with same title or url
            stmt = select(DownloadTask).where(
                (DownloadTask.feed_item_url == feed_item.link)
                | (DownloadTask.feed_item_title == feed_item.title)
            )
            existing = (await s.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                logger.debug("Skipping already processed feed item: %s", feed_item.title)
                return None

            # 2. Create pending DownloadTask
            task = DownloadTask(
                watchlist_item_id=match_res.watchlist_item.id if match_res.watchlist_item else None,
                feed_item_title=feed_item.title,
                feed_item_url=feed_item.link,
                matched_version=match_res.version,
                matched_releaser=match_res.releaser,
                status="pending",
                mirror_urls=[],
            )
            s.add(task)
            await s.commit()
            await s.refresh(task)

            app_name = match_res.app_name or feed_item.title
            version = match_res.version
            releaser = match_res.releaser
            start_time = time.monotonic()

            # 3. Send notifications
            await self.notification_service.notify_feed_matched(
                app_name=app_name,
                version=version,
                releaser=releaser,
                feed_title=feed_item.title,
            )
            await self.notification_service.notify_download_started(
                app_name=app_name,
                version=version,
                releaser=releaser,
                feed_title=feed_item.title,
            )

            try:
                # 4. Extract mirror links if link is a forum topic
                candidate_links: List[str] = []
                if feed_item.link and (
                    feed_item.link.startswith("http://") or feed_item.link.startswith("https://")
                ):
                    try:
                        extracted = await self.mobilism_extractor.fetch_and_extract(feed_item.link)
                        candidate_links = [ext.url for ext in extracted if ext.url]
                    except Exception as exc:
                        logger.debug("Extraction failed for %s, falling back to direct link: %s", feed_item.link, exc)

                if not candidate_links and feed_item.link:
                    candidate_links = [feed_item.link]

                task.mirror_urls = candidate_links
                task.status = "resolving"
                await s.commit()

                # 5. Resolve candidate link
                package_name = match_res.watchlist_item.package_name if match_res.watchlist_item else None
                resolved = await self.resolver_manager.resolve(candidate_links, package_name=package_name)
                if not resolved:
                    raise Exception(f"No resolver could unrestrict candidate links: {candidate_links}")

                task.resolved_url = resolved.download_url
                task.download_tier = getattr(resolved, "tier", None)
                task.status = "downloading"
                await s.commit()

                # 6. Stream file download to staging
                downloaded_file = await self.download_engine.download(
                    url_or_resolved=resolved,
                    destination=self.staging_dir,
                )

                # 7. Extract archive if needed
                if self.archive_extractor.is_archive(downloaded_file):
                    extracted_apks = self.archive_extractor.extract(
                        archive_or_apk_path=downloaded_file,
                        destination_dir=self.staging_dir,
                        flatten=True,
                    )
                    primary_apk = extracted_apks[0]
                else:
                    primary_apk = downloaded_file

                # 8. Organize into standard Nextcloud destination folder
                organized = self.file_organizer.organize(
                    source_file=primary_apk,
                    app_name=app_name,
                    version=version,
                    releaser=releaser,
                )

                elapsed_seconds = time.monotonic() - start_time

                # 9. Mark task completed
                task.file_path = str(organized.destination_path)
                task.file_size = organized.filesize
                task.status = "completed"
                task.completed_at = utcnow()

                # 10. Record history
                history = DownloadHistory(
                    task_id=task.id,
                    app_name=app_name,
                    version=version,
                    releaser=releaser,
                    target_path=str(organized.destination_path),
                    file_size=organized.filesize,
                    duration_seconds=elapsed_seconds,
                    download_tier=task.download_tier,
                    status="completed",
                )
                s.add(history)
                await s.commit()
                await s.refresh(task)

                # 11. Trigger Nextcloud OCC scan
                await self.nextcloud_client.trigger_occ_scan(path=organized.destination_path)

                # 12. Send completion notification
                await self.notification_service.notify_download_completed(
                    app_name=app_name,
                    version=version,
                    releaser=releaser,
                    target_path=str(organized.destination_path),
                    file_size=organized.filesize,
                    download_tier=task.download_tier,
                )

                return task

            except Exception as exc:
                elapsed_seconds = time.monotonic() - start_time
                logger.exception("Failed processing release '%s': %s", feed_item.title, exc)
                task.status = "failed"
                task.error_message = str(exc)
                task.completed_at = utcnow()
                await s.commit()

                await self.notification_service.notify_download_failed(
                    app_name=app_name,
                    version=version,
                    releaser=releaser,
                    error=str(exc),
                )
                return task

        if session is not None:
            return await _run_process(session)
        else:
            async with self.session_factory() as s:
                return await _run_process(s)
