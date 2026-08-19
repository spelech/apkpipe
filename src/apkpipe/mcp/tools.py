"""MCP 2026-07-28 (RC) Tool Registry and Handlers for APKPipe."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union
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
from apkpipe.downloader.engine import DownloadEngine
from apkpipe.downloader.organizer import FileOrganizer
from apkpipe.extractors.scraper_client import PlaywrightScraperClient
from apkpipe.feeds.matcher import match_feed_item
from apkpipe.feeds.parser import extract_title_metadata, parse_feed
from apkpipe.integrations.nextcloud import NextcloudClient
from apkpipe.resolvers.manager import ResolutionManager, ResolverManager
from apkpipe.resolvers.real_debrid import RealDebridResolver

logger = logging.getLogger(__name__)


def _get_writable_dir(preferred_path: Optional[str], default_name: str) -> Path:
    """Return configured directory if writable/creatable, otherwise a safe temp dir fallback."""
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


def make_tool_result(text_or_data: Any, is_error: bool = False) -> Dict[str, Any]:
    """Format output data or error into standard MCP tool result structure."""
    if isinstance(text_or_data, str):
        text = text_or_data
    else:
        text = json.dumps(text_or_data, default=str, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


# ==========================================
# Tool Definitions (Schemas)
# ==========================================

TOOL_LIST_WATCHLIST: Dict[str, Any] = {
    "name": "apkpipe__list_watchlist",
    "description": "List all monitored applications in the watchlist with optional filters.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "enabled_only": {
                "type": "boolean",
                "description": "Filter by enabled status only",
                "default": False,
            },
            "category": {
                "type": "string",
                "description": "Filter by application category",
            },
            "query": {
                "type": "string",
                "description": "Search term matching app name or package name",
            },
        },
    },
}

TOOL_ADD_TO_WATCHLIST: Dict[str, Any] = {
    "name": "apkpipe__add_to_watchlist",
    "description": "Add a new application to the watchlist for release monitoring.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Name of the application to watch",
            },
            "package_name": {
                "type": "string",
                "description": "Android package identifier (e.g. com.example.app)",
            },
            "title_regex": {
                "type": "string",
                "description": "Regex pattern to match release titles",
            },
            "min_version": {
                "type": "string",
                "description": "Minimum acceptable version (SemVer or build string)",
                "default": "0.0.0",
            },
            "releaser_whitelist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Allowed releaser names",
            },
            "releaser_blacklist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Disallowed releaser names",
            },
            "category": {
                "type": "string",
                "description": "Application category",
                "default": "Apps",
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether the watchlist item is active",
                "default": True,
            },
        },
        "required": ["app_name"],
    },
}

TOOL_REMOVE_FROM_WATCHLIST: Dict[str, Any] = {
    "name": "apkpipe__remove_from_watchlist",
    "description": "Disable or permanently delete a watchlist entry.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "watchlist_id": {
                "type": "integer",
                "description": "ID of the watchlist item to remove",
            },
            "app_name": {
                "type": "string",
                "description": "App name of the watchlist item to remove if ID not provided",
            },
            "delete": {
                "type": "boolean",
                "description": "If true, permanently delete from database; if false, set enabled=False",
                "default": False,
            },
        },
    },
}

TOOL_SEARCH_FEED: Dict[str, Any] = {
    "name": "apkpipe__search_feed",
    "description": "Search parsed RSS/Atom release feeds by keyword or regex pattern.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword or regex pattern",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Whether query is a regex pattern",
                "default": False,
            },
            "feed_url": {
                "type": "string",
                "description": "Optional specific feed URL or raw XML content",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}

TOOL_TRIGGER_POLL: Dict[str, Any] = {
    "name": "apkpipe__trigger_poll",
    "description": "Immediately trigger feed polling and matching against active watchlist items.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "integer",
                "description": "Optional ID of a specific feed source to poll",
            },
        },
    },
}

TOOL_DOWNLOAD_URL: Dict[str, Any] = {
    "name": "apkpipe__download_url",
    "description": "Manually enqueue or resolve and download a release URL, with optional Nextcloud ingestion.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Direct download URL, hoster link, or forum topic URL",
            },
            "app_name": {
                "type": "string",
                "description": "Optional application name",
            },
            "version": {
                "type": "string",
                "description": "Optional version string",
            },
            "releaser": {
                "type": "string",
                "description": "Optional releaser name",
            },
            "category": {
                "type": "string",
                "description": "Category for storage organization",
                "default": "Apps",
            },
            "trigger_ingest": {
                "type": "boolean",
                "description": "Whether to trigger Nextcloud OCC scan upon completion",
                "default": True,
            },
            "auto_resolve": {
                "type": "boolean",
                "description": "Whether to resolve and download immediately or just enqueue",
                "default": True,
            },
        },
        "required": ["url"],
    },
}

TOOL_GET_HISTORY: Dict[str, Any] = {
    "name": "apkpipe__get_history",
    "description": "Query past download history and audit log.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of history records to return",
                "default": 20,
            },
            "status": {
                "type": "string",
                "description": "Optional filter by status (e.g. completed, failed)",
            },
            "app_name": {
                "type": "string",
                "description": "Optional filter by app name",
            },
        },
    },
}

TOOL_GET_SYSTEM_STATUS: Dict[str, Any] = {
    "name": "apkpipe__get_system_status",
    "description": "Return overall system health, database metrics, service configurations, and storage stats.",
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOLS: List[Dict[str, Any]] = [
    TOOL_LIST_WATCHLIST,
    TOOL_ADD_TO_WATCHLIST,
    TOOL_REMOVE_FROM_WATCHLIST,
    TOOL_SEARCH_FEED,
    TOOL_TRIGGER_POLL,
    TOOL_DOWNLOAD_URL,
    TOOL_GET_HISTORY,
    TOOL_GET_SYSTEM_STATUS,
]


# ==========================================
# Tool Handler Implementations
# ==========================================


async def list_watchlist_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__list_watchlist."""
    enabled_only = bool(arguments.get("enabled_only", False))
    category = arguments.get("category")
    query = arguments.get("query")

    async def _execute(s: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(WatchlistItem)
        if enabled_only:
            stmt = stmt.where(WatchlistItem.enabled.is_(True))
        if category:
            stmt = stmt.where(WatchlistItem.category == category)

        items = (await s.execute(stmt)).scalars().all()

        if query:
            q_clean = query.strip().lower()
            items = [
                i
                for i in items
                if (i.app_name and q_clean in i.app_name.lower())
                or (i.package_name and q_clean in i.package_name.lower())
            ]

        results = []
        for i in items:
            results.append(
                {
                    "id": i.id,
                    "app_name": i.app_name,
                    "package_name": i.package_name,
                    "title_regex": i.title_regex,
                    "min_version": i.min_version,
                    "releaser_whitelist": i.releaser_whitelist,
                    "releaser_blacklist": i.releaser_blacklist,
                    "enabled": i.enabled,
                    "category": i.category,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "updated_at": i.updated_at.isoformat() if i.updated_at else None,
                }
            )
        return results

    if session is not None:
        data = await _execute(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            data = await _execute(s)

    return make_tool_result(data)


async def add_to_watchlist_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__add_to_watchlist."""
    app_name = (arguments.get("app_name") or "").strip()
    if not app_name:
        return make_tool_result("app_name is required and cannot be empty", is_error=True)

    title_regex = arguments.get("title_regex")
    if title_regex:
        title_regex = title_regex.strip()
        try:
            re.compile(title_regex)
        except re.error as e:
            return make_tool_result(
                f"Invalid regex pattern '{title_regex}': {e}", is_error=True
            )

    package_name = arguments.get("package_name")
    if package_name:
        package_name = package_name.strip()

    min_version = arguments.get("min_version") or "0.0.0"
    releaser_whitelist = arguments.get("releaser_whitelist") or []
    releaser_blacklist = arguments.get("releaser_blacklist") or []
    category = arguments.get("category") or "Apps"
    enabled = arguments.get("enabled", True)
    if enabled is None:
        enabled = True

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        item = WatchlistItem(
            app_name=app_name,
            package_name=package_name,
            title_regex=title_regex,
            min_version=min_version,
            releaser_whitelist=list(releaser_whitelist),
            releaser_blacklist=list(releaser_blacklist),
            category=category,
            enabled=bool(enabled),
        )
        s.add(item)
        await s.commit()
        await s.refresh(item)
        return {
            "id": item.id,
            "app_name": item.app_name,
            "package_name": item.package_name,
            "title_regex": item.title_regex,
            "min_version": item.min_version,
            "releaser_whitelist": item.releaser_whitelist,
            "releaser_blacklist": item.releaser_blacklist,
            "category": item.category,
            "enabled": item.enabled,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    if session is not None:
        data = await _execute(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            data = await _execute(s)

    return make_tool_result(data)


async def remove_from_watchlist_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__remove_from_watchlist."""
    watchlist_id = arguments.get("watchlist_id")
    app_name = arguments.get("app_name")
    delete = bool(arguments.get("delete", False))

    if watchlist_id is None and not app_name:
        return make_tool_result(
            "Either watchlist_id or app_name must be provided", is_error=True
        )

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        stmt = select(WatchlistItem)
        if watchlist_id is not None:
            stmt = stmt.where(WatchlistItem.id == watchlist_id)
        else:
            stmt = stmt.where(WatchlistItem.app_name == app_name.strip())

        item = (await s.execute(stmt)).scalar_one_or_none()
        if not item:
            return {
                "error": True,
                "message": f"Watchlist item with id={watchlist_id} or app_name='{app_name}' not found",
            }

        item_id = item.id
        name = item.app_name

        if delete:
            await s.delete(item)
            await s.commit()
            return {"error": False, "message": f"Permanently deleted watchlist item '{name}' (id={item_id})"}
        else:
            item.enabled = False
            item.updated_at = utcnow()
            await s.commit()
            return {"error": False, "message": f"Disabled watchlist item '{name}' (id={item_id})"}

    if session is not None:
        res = await _execute(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            res = await _execute(s)

    if res.get("error"):
        return make_tool_result(res["message"], is_error=True)
    return make_tool_result(res["message"])


async def search_feed_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__search_feed."""
    query = (arguments.get("query") or "").strip()
    if not query:
        return make_tool_result("query is required", is_error=True)

    is_regex = bool(arguments.get("is_regex", False))
    feed_url = arguments.get("feed_url")
    limit = int(arguments.get("limit", 20))

    feed_sources_content: List[str] = []

    if feed_url:
        if feed_url.startswith("http://") or feed_url.startswith("https://"):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(feed_url)
                    feed_sources_content.append(resp.text)
            except Exception as exc:
                return make_tool_result(
                    f"Failed to fetch feed from '{feed_url}': {exc}", is_error=True
                )
        else:
            feed_sources_content.append(feed_url)
    else:
        # Load feed sources from DB
        async def _get_feed_sources(s: AsyncSession) -> List[str]:
            stmt = select(FeedSource).where(FeedSource.enabled.is_(True))
            sources = (await s.execute(stmt)).scalars().all()
            return [s.url for s in sources]

        if session is not None:
            urls = await _get_feed_sources(session)
        else:
            factory = get_session_factory()
            async with factory() as s:
                urls = await _get_feed_sources(s)

        for u in urls:
            if u.startswith("http://") or u.startswith("https://"):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(u)
                        feed_sources_content.append(resp.text)
                except Exception as exc:
                    logger.warning("Error fetching feed %s: %s", u, exc)
            else:
                feed_sources_content.append(u)

    # Compile regex pattern if requested
    regex_pattern = None
    if is_regex:
        try:
            regex_pattern = re.compile(query, re.IGNORECASE)
        except re.error as exc:
            return make_tool_result(
                f"Invalid search regex pattern '{query}': {exc}", is_error=True
            )

    matched_items = []
    for content in feed_sources_content:
        parsed_items = parse_feed(content)
        for item in parsed_items:
            matches = False
            if regex_pattern:
                if regex_pattern.search(item.title) or regex_pattern.search(item.description):
                    matches = True
            else:
                q_lower = query.lower()
                if q_lower in item.title.lower() or q_lower in item.description.lower():
                    matches = True

            if matches:
                meta = extract_title_metadata(item.title)
                matched_items.append(
                    {
                        "title": item.title,
                        "link": item.link,
                        "description": item.description,
                        "published_at": item.published_at.isoformat() if item.published_at else None,
                        "app_name": meta.app_name,
                        "version": meta.version,
                        "releaser": meta.releaser,
                        "tags": meta.tags,
                    }
                )
                if len(matched_items) >= limit:
                    break
        if len(matched_items) >= limit:
            break

    return make_tool_result(matched_items)


async def trigger_poll_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__trigger_poll."""
    feed_id = arguments.get("feed_id")

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        # 1. Load active watchlist items
        wl_stmt = select(WatchlistItem).where(WatchlistItem.enabled.is_(True))
        watchlist_items = (await s.execute(wl_stmt)).scalars().all()

        # 2. Load feed sources
        feed_stmt = select(FeedSource)
        if feed_id is not None:
            feed_stmt = feed_stmt.where(FeedSource.id == feed_id)
        else:
            feed_stmt = feed_stmt.where(FeedSource.enabled.is_(True))

        feed_sources = (await s.execute(feed_stmt)).scalars().all()

        total_checked = 0
        matches_found = 0
        tasks_created = 0
        matched_details = []

        for source in feed_sources:
            # Fetch feed content
            feed_content = source.url
            if source.url.startswith("http://") or source.url.startswith("https://"):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.get(source.url)
                        feed_content = resp.text
                except Exception as exc:
                    logger.warning("Failed to fetch feed %s during poll: %s", source.url, exc)
                    continue

            items = parse_feed(feed_content)
            total_checked += len(items)

            for item in items:
                match_res = match_feed_item(item, watchlist_items)
                if match_res and match_res.matched:
                    matches_found += 1
                    # Check if a task already exists for this link or title
                    existing_stmt = select(DownloadTask).where(
                        (DownloadTask.feed_item_url == item.link)
                        | (DownloadTask.feed_item_title == item.title)
                    )
                    existing = (await s.execute(existing_stmt)).scalar_one_or_none()

                    if not existing:
                        task = DownloadTask(
                            watchlist_item=match_res.watchlist_item,
                            feed_item_title=item.title,
                            feed_item_url=item.link,
                            matched_version=match_res.version,
                            matched_releaser=match_res.releaser,
                            status="pending",
                        )
                        s.add(task)
                        tasks_created += 1

                    matched_details.append(
                        {
                            "title": item.title,
                            "link": item.link,
                            "app_name": match_res.app_name,
                            "version": match_res.version,
                            "releaser": match_res.releaser,
                            "matched_watchlist_id": match_res.watchlist_item.id if match_res.watchlist_item else None,
                        }
                    )

            source.last_polled_at = utcnow()

        await s.commit()

        return {
            "polled_feeds": len(feed_sources),
            "items_checked": total_checked,
            "matches_found": matches_found,
            "tasks_created": tasks_created,
            "matched_items": matched_details,
        }

    if session is not None:
        data = await _execute(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            data = await _execute(s)

    return make_tool_result(data)


async def download_url_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__download_url."""
    url = (arguments.get("url") or "").strip()
    if not url:
        return make_tool_result("url is required and cannot be empty", is_error=True)

    app_name = arguments.get("app_name")
    version = arguments.get("version")
    releaser = arguments.get("releaser")
    category = arguments.get("category") or "Apps"
    trigger_ingest = bool(arguments.get("trigger_ingest", True))
    auto_resolve = bool(arguments.get("auto_resolve", True))

    if not app_name:
        meta = extract_title_metadata(url)
        app_name = meta.app_name or Path(urllib.parse.urlparse(url).path).stem or "ManualDownload"
        if not version:
            version = meta.version
        if not releaser:
            releaser = meta.releaser

    async def _execute(s: AsyncSession) -> Dict[str, Any]:
        task = DownloadTask(
            feed_item_title=app_name,
            feed_item_url=url,
            matched_version=version,
            matched_releaser=releaser,
            status="pending",
        )
        s.add(task)
        await s.commit()
        await s.refresh(task)

        if not auto_resolve:
            return {
                "task_id": task.id,
                "app_name": app_name,
                "status": task.status,
                "url": url,
                "auto_resolve": False,
            }

        # Auto resolve and download
        settings = get_settings()
        staging_dir = _get_writable_dir(settings.staging_dir, "apkpipe_staging")
        download_dir = _get_writable_dir(settings.download_dir, "apkpipe_downloads")

        rd_resolver = RealDebridResolver(api_token=settings.real_debrid_api_token) if settings.real_debrid_api_token else None
        resolver_mgr = ResolutionManager(rd_resolver=rd_resolver)
        downloader = DownloadEngine(staging_dir=staging_dir)
        organizer = FileOrganizer(base_download_dir=download_dir)

        try:
            # 1. Resolve
            task.status = "resolving"
            await s.commit()

            resolved = await resolver_mgr.resolve(url)
            task.resolved_url = resolved.download_url
            task.download_tier = resolved.tier
            task.status = "downloading"
            await s.commit()

            # 2. Download
            downloaded_path = await downloader.download(
                url_or_resolved=resolved,
                destination=staging_dir,
            )

            # 3. Organize / Store
            organized = organizer.organize(
                source_file=downloaded_path,
                app_name=app_name,
                version=version,
                releaser=releaser,
            )
            final_path = organized.destination_path
            file_size = organized.filesize

            task.file_path = str(final_path)
            task.file_size = file_size
            task.status = "completed"
            task.completed_at = utcnow()

            # 4. Record history
            history = DownloadHistory(
                task=task,
                app_name=app_name,
                version=version,
                releaser=releaser,
                target_path=str(final_path),
                file_size=file_size,
                download_tier=resolved.tier,
                status="completed",
            )
            s.add(history)
            await s.commit()
            await s.refresh(task)

            # 5. Nextcloud OCC ingest if configured and requested
            if trigger_ingest and settings.nextcloud_url:
                try:
                    nc_client = NextcloudClient(
                        nextcloud_url=settings.nextcloud_url,
                        token=settings.nextcloud_token,
                        custom_command=settings.nextcloud_occ_command,
                    )
                    await nc_client.scan_file(str(final_path))
                except Exception as nc_err:
                    logger.warning("Nextcloud OCC scan error: %s", nc_err)

            return {
                "task_id": task.id,
                "app_name": app_name,
                "version": version,
                "releaser": releaser,
                "status": task.status,
                "file_path": task.file_path,
                "download_tier": task.download_tier,
                "file_size": task.file_size,
            }

        except Exception as exc:
            logger.exception("Error processing download for %s: %s", url, exc)
            task.status = "failed"
            task.error_message = str(exc)
            await s.commit()
            raise

    try:
        if session is not None:
            data = await _execute(session)
        else:
            factory = get_session_factory()
            async with factory() as s:
                data = await _execute(s)
        return make_tool_result(data)
    except Exception as exc:
        return make_tool_result(f"Download processing failed: {exc}", is_error=True)


async def get_history_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__get_history."""
    limit = int(arguments.get("limit", 20))
    status = arguments.get("status")
    app_name = arguments.get("app_name")

    async def _execute(s: AsyncSession) -> List[Dict[str, Any]]:
        stmt = select(DownloadHistory).order_by(
            DownloadHistory.downloaded_at.desc(), DownloadHistory.id.desc()
        )
        if status:
            stmt = stmt.where(DownloadHistory.status == status)
        if app_name:
            stmt = stmt.where(DownloadHistory.app_name.ilike(f"%{app_name.strip()}%"))
        stmt = stmt.limit(limit)

        records = (await s.execute(stmt)).scalars().all()
        results = []
        for r in records:
            results.append(
                {
                    "id": r.id,
                    "task_id": r.task_id,
                    "app_name": r.app_name,
                    "version": r.version,
                    "releaser": r.releaser,
                    "target_path": r.target_path,
                    "file_size": r.file_size,
                    "duration_seconds": r.duration_seconds,
                    "download_tier": r.download_tier,
                    "status": r.status,
                    "downloaded_at": r.downloaded_at.isoformat() if r.downloaded_at else None,
                }
            )
        return results

    if session is not None:
        data = await _execute(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            data = await _execute(s)

    return make_tool_result(data)


async def get_system_status_tool(
    arguments: Dict[str, Any], session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Handler for apkpipe__get_system_status."""
    settings = get_settings()

    async def _get_db_stats(s: AsyncSession) -> Dict[str, Any]:
        wl_count = (await s.execute(select(func.count(WatchlistItem.id)))).scalar() or 0
        feed_count = (await s.execute(select(func.count(FeedSource.id)))).scalar() or 0
        active_feed_count = (
            await s.execute(
                select(func.count(FeedSource.id)).where(FeedSource.enabled.is_(True))
            )
        ).scalar() or 0
        task_count = (await s.execute(select(func.count(DownloadTask.id)))).scalar() or 0
        history_count = (await s.execute(select(func.count(DownloadHistory.id)))).scalar() or 0

        return {
            "status": "connected",
            "watchlist_count": wl_count,
            "feeds_total": feed_count,
            "feeds_active": active_feed_count,
            "tasks_count": task_count,
            "history_count": history_count,
        }

    if session is not None:
        db_stats = await _get_db_stats(session)
    else:
        factory = get_session_factory()
        async with factory() as s:
            db_stats = await _get_db_stats(s)

    # Services info
    services_info = {
        "real_debrid_configured": bool(settings.real_debrid_api_token),
        "jdownloader_configured": bool(settings.jdownloader_email),
        "nextcloud_configured": bool(settings.nextcloud_url),
        "apprise_configured": bool(settings.apprise_url),
        "ntfy_configured": bool(settings.ntfy_topic),
    }

    # Storage info
    dl_path = settings.download_dir
    staging_path = settings.staging_dir
    disk_target = dl_path if os.path.exists(dl_path) else "/"
    try:
        usage = shutil.disk_usage(disk_target)
        storage_info = {
            "download_dir": dl_path,
            "staging_dir": staging_path,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100.0, 2) if usage.total > 0 else 0,
        }
    except Exception as exc:
        storage_info = {
            "download_dir": dl_path,
            "staging_dir": staging_path,
            "error": str(exc),
        }

    status_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_stats,
        "services": services_info,
        "storage": storage_info,
    }

    return make_tool_result(status_data)


# ==========================================
# Tool Registry Map & Dispatcher
# ==========================================

TOOL_REGISTRY: Dict[
    str, Callable[[Dict[str, Any], Optional[AsyncSession]], Coroutine[Any, Any, Dict[str, Any]]]
] = {
    "apkpipe__list_watchlist": list_watchlist_tool,
    "apkpipe__add_to_watchlist": add_to_watchlist_tool,
    "apkpipe__remove_from_watchlist": remove_from_watchlist_tool,
    "apkpipe__search_feed": search_feed_tool,
    "apkpipe__trigger_poll": trigger_poll_tool,
    "apkpipe__download_url": download_url_tool,
    "apkpipe__get_history": get_history_tool,
    "apkpipe__get_system_status": get_system_status_tool,
}


async def execute_tool(
    name: str,
    arguments: Optional[Dict[str, Any]] = None,
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Execute a registered MCP tool by name."""
    handler = TOOL_REGISTRY.get(name)
    if not handler:
        return make_tool_result(f"Tool '{name}' not found in registry", is_error=True)

    args = arguments or {}
    try:
        return await handler(args, session)
    except Exception as exc:
        logger.exception("Error executing MCP tool %s: %s", name, exc)
        return make_tool_result(f"Tool execution failed: {exc}", is_error=True)
