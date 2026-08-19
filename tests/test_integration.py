"""Comprehensive End-to-End Integration Tests for APKPipe.

Exercises the complete pipeline flow:
Feed ingestion -> Watchlist matching -> Tier 1 Real-Debrid resolution ->
Stream download -> Archive extraction -> Nextcloud OCC scan ->
Apprise notification -> Download history recording -> MCP search & trigger -> REST API endpoints.
"""

import asyncio
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import zipfile

import httpx
import pytest
from sqlalchemy import func, select

from apkpipe.api import downloads_router, feeds_router, mcp_router, settings_router, watchlist_router
from apkpipe.config import Settings, get_settings
from apkpipe.database.db import close_db, get_session_factory, init_db
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
from apkpipe.downloader.organizer import FileOrganizer
from apkpipe.extractors.mobilism import MobilismExtractor
from apkpipe.extractors.scraper_client import PlaywrightScraperClient
from apkpipe.feeds.matcher import match_feed_item
from apkpipe.feeds.parser import FeedItem, parse_feed
from apkpipe.feeds.poller import FeedPoller
from apkpipe.integrations.nextcloud import NextcloudClient, OccScanResult
from apkpipe.main import create_app
from apkpipe.mcp.tools import TOOL_REGISTRY, execute_tool
from apkpipe.notifications.apprise import NotificationEvent, NotificationService
from apkpipe.resolvers.base import ResolvedDownload
from apkpipe.resolvers.manager import ResolutionManager
from apkpipe.resolvers.real_debrid import RealDebridResolver


# Sample RSS Feed with multiple releases
SAMPLE_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Mobilism Releases</title>
    <link>https://forum.mobilism.org</link>
    <description>Android App Releases</description>
    <item>
      <title>Spotify: Music and Podcasts v8.9.18.534 [Balatan]</title>
      <link>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000001</link>
      <description><![CDATA[
        Requirements: Android 5.0+<br/>
        Overview: Play millions of songs and podcasts on your device.<br/>
        Download Instructions:<br/>
        https://rapidgator.net/file/abc123spotify/Spotify_v8.9.18.534.zip.html<br/>
        https://uploady.io/xyzspotify123<br/>
      ]]></description>
      <pubDate>Tue, 18 Aug 2026 12:00:00 GMT</pubDate>
      <guid>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000001</guid>
    </item>
    <item>
      <title>Nova Launcher Prime v8.0.18 [Patched]</title>
      <link>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000002</link>
      <description><![CDATA[
        Requirements: Android 8.0+<br/>
        Overview: The top launcher for modern Android.<br/>
        Download Instructions:<br/>
        https://dropgalaxy.in/nova_launcher_v8.0.18.apk<br/>
      ]]></description>
      <pubDate>Tue, 18 Aug 2026 12:15:00 GMT</pubDate>
      <guid>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000002</guid>
    </item>
    <item>
      <title>Untrusted App v1.0.0 [SpamReleaser]</title>
      <link>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000003</link>
      <description><![CDATA[
        Download Instructions: https://rapidgator.net/file/spam/spam.apk
      ]]></description>
      <pubDate>Tue, 18 Aug 2026 12:30:00 GMT</pubDate>
      <guid>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=5000003</guid>
    </item>
  </channel>
</rss>
"""


def _create_dummy_zip_apk(apk_filename: str = "Spotify.apk", content: bytes = b"DUMMY_APK_DEX_HEADER_12345") -> bytes:
    """Create in-memory zip archive bytes containing an APK file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(apk_filename, content)
    return buf.getvalue()


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup and teardown in-memory test database for each integration test."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = await init_db(test_db_url)
    yield engine
    await close_db()


@pytest.fixture
def temp_dirs():
    """Create isolated temporary staging and download directories."""
    with tempfile.TemporaryDirectory() as staging, tempfile.TemporaryDirectory() as downloads:
        yield Path(staging), Path(downloads)


# =========================================================================
# Integration Test 1: Complete Pipeline Flow (RSS -> RD -> Extract -> OCC -> Notify -> History)
# =========================================================================

@pytest.mark.asyncio
async def test_full_pipeline_e2e(temp_dirs):
    """Test full end-to-end flow from RSS parsing to storage, scan, and notification recording."""
    staging_dir, download_dir = temp_dirs
    session_factory = get_session_factory()

    # 1. Populate Watchlist and FeedSource in SQLite
    async with session_factory() as session:
        wl_item = WatchlistItem(
            app_name="Spotify",
            package_name="com.spotify.music",
            title_regex="Spotify",
            min_version="8.9.0",
            releaser_whitelist=["Balatan"],
            releaser_blacklist=["MaliciousUser"],
            category="Music",
            enabled=True,
        )
        feed_source = FeedSource(
            name="Mobilism Android Apps",
            url="https://forum.mobilism.org/feed.xml",
            feed_type="mobilism_rss",
            enabled=True,
            poll_interval_minutes=15,
        )
        session.add(wl_item)
        session.add(feed_source)
        await session.commit()
        await session.refresh(wl_item)
        await session.refresh(feed_source)

    # 2. Prepare Mock Services and Real Components
    zip_bytes = _create_dummy_zip_apk("Spotify_v8.9.18.534.apk", b"PK\x03\x04_SPOTIFY_DUMMY_BYTECODE_DATA_")
    
    # Mock Real-Debrid Resolver
    mock_rd_resolver = AsyncMock(spec=RealDebridResolver)
    mock_rd_resolver.can_resolve.return_value = True
    mock_rd_resolver.resolve.return_value = ResolvedDownload(
        original_link="https://rapidgator.net/file/abc123spotify/Spotify_v8.9.18.534.zip.html",
        download_url="https://download.real-debrid.com/d/xyz/Spotify_v8.9.18.534.zip",
        filename="Spotify_v8.9.18.534.zip",
        filesize=len(zip_bytes),
        tier="tier_1_real_debrid",
        hoster="rapidgator.net",
    )

    resolver_manager = ResolutionManager(rd_resolver=mock_rd_resolver)

    # Mock Download Engine to return actual zip bytes written to staging
    download_engine = DownloadEngine(staging_dir=staging_dir)
    
    async def mock_download_stream(url_or_resolved, destination=None, **kwargs):
        dest = Path(destination) if destination else staging_dir
        dest.mkdir(parents=True, exist_ok=True)
        file_path = dest / "Spotify_v8.9.18.534.zip"
        file_path.write_bytes(zip_bytes)
        return file_path

    download_engine.download = AsyncMock(side_effect=mock_download_stream)

    # Real Archive Extractor and File Organizer
    archive_extractor = ArchiveExtractor(temp_dir=staging_dir)
    file_organizer = FileOrganizer(base_download_dir=download_dir)

    # Mock Nextcloud Client & Apprise Notifications
    mock_nextcloud = AsyncMock(spec=NextcloudClient)
    mock_nextcloud.trigger_occ_scan.return_value = OccScanResult(
        success=True,
        output="Scanned 1 file in 0.05s",
        strategy_used="docker_exec",
        scanned_files_count=1,
        scanned_folders_count=1,
    )

    mock_notifier = AsyncMock(spec=NotificationService)
    mock_notifier.notify_feed_matched.return_value = True
    mock_notifier.notify_download_started.return_value = True
    mock_notifier.notify_download_completed.return_value = True
    mock_notifier.notify_download_failed.return_value = True

    # Build FeedPoller
    poller = FeedPoller(
        poll_interval_seconds=60,
        session_factory=session_factory,
        resolver_manager=resolver_manager,
        download_engine=download_engine,
        archive_extractor=archive_extractor,
        file_organizer=file_organizer,
        nextcloud_client=mock_nextcloud,
        notification_service=mock_notifier,
    )

    # Inject feed content fetcher mock to return SAMPLE_RSS_FEED
    poller._fetch_feed_content = AsyncMock(return_value=SAMPLE_RSS_FEED)

    # 3. Execute feed polling cycle
    poll_result = await poller.poll_all_feeds()
    
    assert poll_result["status"] == "ok"
    assert poll_result["polled_feeds"] == 1
    assert poll_result["items_checked"] == 3
    assert poll_result["matches_found"] == 1
    assert poll_result["tasks_created"] == 1
    assert poll_result["tasks_completed"] == 1

    # 4. Verify DownloadTask in Database
    async with session_factory() as session:
        tasks_stmt = select(DownloadTask).order_by(DownloadTask.id.desc())
        tasks = (await session.execute(tasks_stmt)).scalars().all()
        assert len(tasks) == 1
        task = tasks[0]
        assert task.status == "completed"
        assert task.feed_item_title == "Spotify: Music and Podcasts v8.9.18.534 [Balatan]"
        assert task.matched_version == "8.9.18.534"
        assert task.matched_releaser == "Balatan"
        assert task.download_tier == "tier_1_real_debrid"
        assert task.file_size == len(b"PK\x03\x04_SPOTIFY_DUMMY_BYTECODE_DATA_")
        assert task.completed_at is not None
        assert Path(task.file_path).is_file()

        # 5. Verify DownloadHistory in Database
        history_stmt = select(DownloadHistory).order_by(DownloadHistory.id.desc())
        histories = (await session.execute(history_stmt)).scalars().all()
        assert len(histories) == 1
        hist = histories[0]
        assert hist.app_name == "Spotify: Music and Podcasts"
        assert hist.version == "8.9.18.534"
        assert hist.releaser == "Balatan"
        assert hist.status == "completed"
        assert hist.task_id == task.id
        assert hist.target_path == task.file_path
        assert hist.download_tier == "tier_1_real_debrid"
        assert hist.file_size == task.file_size
        assert hist.duration_seconds >= 0.0

    # 6. Verify Filesystem Placement and file content
    organized_apk = Path(task.file_path)
    assert organized_apk.is_file()
    assert organized_apk.read_bytes() == b"PK\x03\x04_SPOTIFY_DUMMY_BYTECODE_DATA_"

    # 7. Verify Nextcloud OCC Scan Trigger
    mock_nextcloud.trigger_occ_scan.assert_awaited_once_with(path=organized_apk)

    # 8. Verify Notification Dispatches
    mock_notifier.notify_feed_matched.assert_awaited_once_with(
        app_name=hist.app_name,
        version="8.9.18.534",
        releaser="Balatan",
        feed_title="Spotify: Music and Podcasts v8.9.18.534 [Balatan]",
    )
    mock_notifier.notify_download_started.assert_awaited_once_with(
        app_name=hist.app_name,
        version="8.9.18.534",
        releaser="Balatan",
        feed_title="Spotify: Music and Podcasts v8.9.18.534 [Balatan]",
    )
    mock_notifier.notify_download_completed.assert_awaited_once_with(
        app_name=hist.app_name,
        version="8.9.18.534",
        releaser="Balatan",
        target_path=task.file_path,
        file_size=len(b"PK\x03\x04_SPOTIFY_DUMMY_BYTECODE_DATA_"),
        download_tier="tier_1_real_debrid",
    )


# =========================================================================
# Integration Test 2: Direct APK Download Flow (No Archive)
# =========================================================================

@pytest.mark.asyncio
async def test_direct_apk_download_flow(temp_dirs):
    """Test pipeline handling direct APK download without requiring zip extraction."""
    staging_dir, download_dir = temp_dirs
    session_factory = get_session_factory()

    async with session_factory() as session:
        wl_item = WatchlistItem(
            app_name="Nova Launcher",
            title_regex="Nova Launcher",
            min_version="8.0.0",
            releaser_whitelist=["Balatan"],
            enabled=True,
        )
        session.add(wl_item)
        await session.commit()
        await session.refresh(wl_item)

    apk_bytes = b"DIRECT_APK_PACKAGE_BYTES_998877"

    # Mock resolver
    mock_rd = AsyncMock(spec=RealDebridResolver)
    mock_rd.can_resolve.return_value = True
    mock_rd.resolve.return_value = ResolvedDownload(
        original_link="https://dropgalaxy.in/nova_launcher_v8.0.18.apk",
        download_url="https://direct.download/nova.apk",
        filename="nova_launcher_v8.0.18.apk",
        filesize=len(apk_bytes),
        tier="tier_1_real_debrid",
    )
    resolver_manager = ResolutionManager(rd_resolver=mock_rd)

    download_engine = DownloadEngine(staging_dir=staging_dir)

    async def mock_direct_dl(url_or_resolved, destination=None, **kwargs):
        dest = Path(destination) if destination else staging_dir
        dest.mkdir(parents=True, exist_ok=True)
        fp = dest / "nova_launcher_v8.0.18.apk"
        fp.write_bytes(apk_bytes)
        return fp

    download_engine.download = AsyncMock(side_effect=mock_direct_dl)

    archive_extractor = ArchiveExtractor(temp_dir=staging_dir)
    file_organizer = FileOrganizer(base_download_dir=download_dir)
    mock_nextcloud = AsyncMock(spec=NextcloudClient)
    mock_notifier = AsyncMock(spec=NotificationService)

    poller = FeedPoller(
        poll_interval_seconds=60,
        session_factory=session_factory,
        resolver_manager=resolver_manager,
        download_engine=download_engine,
        archive_extractor=archive_extractor,
        file_organizer=file_organizer,
        nextcloud_client=mock_nextcloud,
        notification_service=mock_notifier,
    )

    feed_item = FeedItem(
        title="Nova Launcher Prime v8.0.18 [Balatan]",
        link="https://dropgalaxy.in/nova_launcher_v8.0.18.apk",
        description="Nova launcher direct apk link",
        published_at=datetime.now(timezone.utc),
    )

    async with session_factory() as session:
        wl_items = (await session.execute(select(WatchlistItem))).scalars().all()
        task = await poller.process_item(feed_item, wl_items, session=session)

    assert task is not None
    assert task.status == "completed"
    assert task.matched_version == "8.0.18"
    assert task.matched_releaser == "Balatan"
    assert Path(task.file_path).is_file()
    assert Path(task.file_path).read_bytes() == apk_bytes


# =========================================================================
# Integration Test 3: Releaser Filter Rejection & Version Gating
# =========================================================================

@pytest.mark.asyncio
async def test_releaser_filter_and_version_gating():
    """Verify releases with untrusted releasers or older versions are ignored."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        wl_item = WatchlistItem(
            app_name="Spotify",
            title_regex="Spotify",
            min_version="8.9.0",
            releaser_whitelist=["Balatan", "derrin"],
            releaser_blacklist=["SpamReleaser"],
            enabled=True,
        )
        session.add(wl_item)
        await session.commit()
        await session.refresh(wl_item)

    poller = FeedPoller(session_factory=session_factory)

    # 1. Untrusted releaser
    untrusted_item = FeedItem(
        title="Spotify: Music and Podcasts v8.9.18.534 [SpamReleaser]",
        link="https://forum.mobilism.org/viewtopic.php?t=1",
        description="Spam",
        published_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        wl_items = (await session.execute(select(WatchlistItem))).scalars().all()
        result = await poller.process_item(untrusted_item, wl_items, session=session)
    assert result is None

    # 2. Older version than min_version
    old_version_item = FeedItem(
        title="Spotify: Music and Podcasts v8.8.5.100 [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=2",
        description="Old version",
        published_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        wl_items = (await session.execute(select(WatchlistItem))).scalars().all()
        result = await poller.process_item(old_version_item, wl_items, session=session)
    assert result is None


# =========================================================================
# Integration Test 4: Pipeline Failure Handling & Error Notification
# =========================================================================

@pytest.mark.asyncio
async def test_pipeline_failure_handling(temp_dirs):
    """Verify that download/resolver failures transition task to failed and send alert."""
    staging_dir, download_dir = temp_dirs
    session_factory = get_session_factory()

    async with session_factory() as session:
        wl_item = WatchlistItem(
            app_name="Spotify",
            title_regex="Spotify",
            min_version="8.9.0",
            releaser_whitelist=["Balatan"],
            enabled=True,
        )
        session.add(wl_item)
        await session.commit()
        await session.refresh(wl_item)

    # Resolver that fails unrestrict
    mock_rd = AsyncMock(spec=RealDebridResolver)
    mock_rd.can_resolve.return_value = True
    mock_rd.resolve.side_effect = RuntimeError("Real-Debrid API rate limit / 503")
    resolver_manager = ResolutionManager(rd_resolver=mock_rd)

    mock_notifier = AsyncMock(spec=NotificationService)

    poller = FeedPoller(
        poll_interval_seconds=60,
        session_factory=session_factory,
        resolver_manager=resolver_manager,
        notification_service=mock_notifier,
    )

    feed_item = FeedItem(
        title="Spotify: Music and Podcasts v8.9.18.534 [Balatan]",
        link="https://rapidgator.net/file/fail.zip",
        description="Failing mirror",
        published_at=datetime.now(timezone.utc),
    )

    async with session_factory() as session:
        wl_items = (await session.execute(select(WatchlistItem))).scalars().all()
        task = await poller.process_item(feed_item, wl_items, session=session)

    assert task is not None
    assert task.status == "failed"
    assert task.error_message is not None and len(task.error_message) > 0

    # Verify failure notification was sent
    mock_notifier.notify_download_failed.assert_awaited_once_with(
        app_name="Spotify: Music and Podcasts",
        version="8.9.18.534",
        releaser="Balatan",
        error=task.error_message,
    )


# =========================================================================
# Integration Test 5: MCP Server Tools End-to-End Orchestration
# =========================================================================

@pytest.mark.asyncio
async def test_mcp_tools_orchestration_workflow():
    """Verify native MCP tools execution across watchlist, search, polling, and status."""
    session_factory = get_session_factory()

    # 1. Verify all 8 standard tools are registered
    expected_tools = [
        "apkpipe__list_watchlist",
        "apkpipe__add_to_watchlist",
        "apkpipe__remove_from_watchlist",
        "apkpipe__search_feed",
        "apkpipe__trigger_poll",
        "apkpipe__download_url",
        "apkpipe__get_history",
        "apkpipe__get_system_status",
    ]
    for tool_name in expected_tools:
        assert tool_name in TOOL_REGISTRY

    async with session_factory() as session:
        # 2. Add application to watchlist via MCP tool
        add_res = await execute_tool(
            "apkpipe__add_to_watchlist",
            {
                "app_name": "Pocket Casts",
                "package_name": "au.com.shiftyjelly.pocketcasts",
                "title_regex": "Pocket Casts",
                "min_version": "7.50.0",
                "releaser_whitelist": ["Balatan"],
                "category": "Podcasts",
            },
            session=session,
        )
        assert add_res["isError"] is False
        add_data = json.loads(add_res["content"][0]["text"])
        assert add_data["app_name"] == "Pocket Casts"
        assert add_data["package_name"] == "au.com.shiftyjelly.pocketcasts"

        # 3. List watchlist via MCP tool
        list_res = await execute_tool("apkpipe__list_watchlist", {"query": "Pocket"}, session=session)
        assert list_res["isError"] is False
        list_data = json.loads(list_res["content"][0]["text"])
        assert len(list_data) == 1
        assert list_data[0]["app_name"] == "Pocket Casts"

        # 4. Search Feed via MCP tool using inline XML or pattern
        search_res = await execute_tool(
            "apkpipe__search_feed",
            {
                "query": "Spotify",
                "feed_url": SAMPLE_RSS_FEED,
            },
            session=session,
        )
        assert search_res["isError"] is False
        search_data = json.loads(search_res["content"][0]["text"])
        assert len(search_data) == 1
        assert "Spotify" in search_data[0]["title"]

        # 5. System Status via MCP tool
        status_res = await execute_tool("apkpipe__get_system_status", {}, session=session)
        assert status_res["isError"] is False
        status_data = json.loads(status_res["content"][0]["text"])
        assert status_data["status"] == "healthy"
        assert "database" in status_data

        # 6. Remove from Watchlist via MCP tool (soft disable and then permanent delete)
        remove_res = await execute_tool(
            "apkpipe__remove_from_watchlist",
            {"app_name": "Pocket Casts", "delete": True},
            session=session,
        )
        assert remove_res["isError"] is False
        assert "deleted" in remove_res["content"][0]["text"].lower()


# =========================================================================
# Integration Test 6: FastAPI REST API End-to-End Workflow
# =========================================================================

@pytest.mark.asyncio
async def test_rest_api_full_flow():
    """Verify REST API routes for health, watchlist, feeds, downloads, and settings."""
    app = create_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        resp = await client.get("/health")
        assert resp.status_code == 200
        health_json = resp.json()
        assert health_json["status"] == "healthy"
        assert "version" in health_json

        # 2. Watchlist REST API CRUD
        create_wl_payload = {
            "app_name": "Smart Launcher",
            "package_name": "ginlemon.flowerfree",
            "title_regex": "Smart Launcher",
            "min_version": "6.4",
            "releaser_whitelist": ["Balatan"],
            "releaser_blacklist": [],
            "category": "Personalization",
            "enabled": True,
        }
        wl_resp = await client.post("/api/watchlist", json=create_wl_payload)
        assert wl_resp.status_code in (200, 201)
        wl_data = wl_resp.json()
        assert wl_data["app_name"] == "Smart Launcher"

        get_wl_resp = await client.get("/api/watchlist")
        assert get_wl_resp.status_code == 200
        assert len(get_wl_resp.json()) >= 1

        # 3. Feed Sources REST API
        feed_payload = {
            "name": "Mobilism Games",
            "url": "https://forum.mobilism.org/feed_games.xml",
            "feed_type": "mobilism_rss",
            "enabled": True,
            "poll_interval_minutes": 30,
        }
        feed_resp = await client.post("/api/feeds", json=feed_payload)
        assert feed_resp.status_code in (200, 201)

        get_feeds_resp = await client.get("/api/feeds")
        assert get_feeds_resp.status_code == 200
        assert len(get_feeds_resp.json()) >= 1

        # 4. Downloads API
        tasks_resp = await client.get("/api/downloads/queue")
        assert tasks_resp.status_code == 200

        history_resp = await client.get("/api/downloads/history")
        assert history_resp.status_code == 200

        # 5. Settings API
        settings_resp = await client.get("/api/settings")
        assert settings_resp.status_code == 200

        # 6. Web UI HTML page routes
        for path in ["/", "/watchlist", "/feeds", "/history", "/settings"]:
            page_resp = await client.get(path)
            assert page_resp.status_code == 200
            assert "text/html" in page_resp.headers["content-type"]
