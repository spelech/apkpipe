"""Unit and integration tests for FeedPoller background polling engine."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import select

from apkpipe.database.db import close_db, get_db, init_db
from apkpipe.database.models import (
    AppSetting,
    DownloadHistory,
    DownloadTask,
    FeedSource,
    WatchlistItem,
)
from apkpipe.feeds.parser import FeedItem
from apkpipe.feeds.poller import FeedPoller
from apkpipe.resolvers.base import ResolvedDownload


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup and teardown in-memory test database for each test."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = await init_db(test_db_url)
    yield engine
    await close_db()


@pytest.mark.asyncio
async def test_poller_initialization():
    """Verify FeedPoller default initialization and attributes."""
    poller = FeedPoller(poll_interval_seconds=60)
    assert poller.poll_interval_seconds == 60
    assert poller.is_running is False
    assert poller._task is None


@pytest.mark.asyncio
async def test_poller_start_and_stop():
    """Verify starting and stopping the background polling task."""
    poller = FeedPoller(poll_interval_seconds=1)
    
    with patch.object(poller, "poll_all_feeds", new_callable=AsyncMock) as mock_poll:
        await poller.start()
        assert poller.is_running is True
        assert poller._task is not None
        
        # Calling start again when already running is idempotent
        await poller.start()
        
        await asyncio.sleep(0.1)
        await poller.stop()
        assert poller.is_running is False
        assert poller._task is None

        # Calling stop when already stopped is safe
        await poller.stop()


@pytest.mark.asyncio
async def test_poll_single_feed_not_found():
    """Verify polling a non-existent feed returns appropriate error or 0 result."""
    poller = FeedPoller()
    res = await poller.poll_single_feed(99999)
    assert res["status"] == "error" or res["polled_feeds"] == 0


@pytest.mark.asyncio
async def test_poll_single_feed_success(tmp_path):
    """Verify polling a single feed by ID matches watchlist and creates download task."""
    sample_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Mobilism Android Releases</title>
        <item>
          <title>Nova Launcher Prime v8.0.18 [Mod] [Balatan]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=1001</link>
          <description>Nova Launcher Prime full version</description>
        </item>
      </channel>
    </rss>
    """
    
    # 1. Insert watchlist item and feed source
    async for session in get_db():
        wl = WatchlistItem(
            app_name="Nova Launcher",
            min_version="8.0.0",
            releaser_whitelist=["Balatan"],
            enabled=True,
        )
        feed = FeedSource(
            name="Test Feed",
            url=sample_feed,
            enabled=True,
        )
        session.add_all([wl, feed])
        await session.commit()
        await session.refresh(feed)
        feed_id = feed.id

    # 2. Mock downloader and resolvers
    dummy_apk = tmp_path / "Nova Launcher Prime v8.0.18 [Balatan].apk"
    dummy_apk.write_bytes(b"dummy apk binary data")

    poller = FeedPoller()
    with patch.object(
        poller.resolver_manager,
        "resolve",
        new_callable=AsyncMock,
        return_value=ResolvedDownload(
            download_url="https://real-debrid.com/d/abc",
            original_link="https://forum.mobilism.org/viewtopic.php?t=1001",
            filename="Nova Launcher Prime v8.0.18 [Balatan].apk",
            tier="real_debrid",
        ),
    ), patch.object(
        poller.download_engine,
        "download",
        new_callable=AsyncMock,
        return_value=dummy_apk,
    ), patch.object(
        poller.nextcloud_client,
        "trigger_occ_scan",
        new_callable=AsyncMock,
    ) as mock_occ:
        res = await poller.poll_single_feed(feed_id)
        assert res["polled_feeds"] == 1
        assert res["matches_found"] == 1
        assert res["tasks_created"] == 1
        assert res["tasks_completed"] == 1

        # Check DB records
        async for session in get_db():
            tasks = (await session.execute(select(DownloadTask))).scalars().all()
            assert len(tasks) == 1
            assert tasks[0].status == "completed"
            assert tasks[0].matched_version == "8.0.18"

            history = (await session.execute(select(DownloadHistory))).scalars().all()
            assert len(history) == 1
            assert "Nova Launcher" in history[0].app_name
            assert history[0].status == "completed"


@pytest.mark.asyncio
async def test_poll_all_feeds_multiple():
    """Verify poll_all_feeds checks all enabled feed sources and skips disabled ones."""
    sample_feed_1 = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>App One v1.0.0 [Balatan]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=10</link>
        </item>
      </channel>
    </rss>
    """
    sample_feed_2 = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>App Two v2.0.0 [derrin]</title>
          <link>https://forum.mobilism.org/viewtopic.php?t=20</link>
        </item>
      </channel>
    </rss>
    """

    async for session in get_db():
        wl1 = WatchlistItem(app_name="App One", enabled=True)
        wl2 = WatchlistItem(app_name="App Two", enabled=True)
        feed1 = FeedSource(name="Feed 1", url=sample_feed_1, enabled=True)
        feed2 = FeedSource(name="Feed 2", url=sample_feed_2, enabled=True)
        feed_disabled = FeedSource(name="Feed Disabled", url="<rss></rss>", enabled=False)
        session.add_all([wl1, wl2, feed1, feed2, feed_disabled])
        await session.commit()

    poller = FeedPoller()
    with patch.object(poller, "process_item", new_callable=AsyncMock) as mock_process:
        mock_task = MagicMock(spec=DownloadTask)
        mock_task.status = "completed"
        mock_process.return_value = mock_task

        res = await poller.poll_all_feeds()
        assert res["polled_feeds"] == 2
        assert mock_process.call_count == 2


@pytest.mark.asyncio
async def test_process_item_deduplication():
    """Verify that existing duplicate tasks are skipped and not re-downloaded."""
    feed_item = FeedItem(
        title="Duplicate App v1.0.0 [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=999",
    )

    async for session in get_db():
        wl = WatchlistItem(app_name="Duplicate App", enabled=True)
        session.add(wl)
        await session.commit()
        await session.refresh(wl)

        # Existing task with same title and link
        task = DownloadTask(
            watchlist_item_id=wl.id,
            feed_item_title=feed_item.title,
            feed_item_url=feed_item.link,
            status="completed",
        )
        session.add(task)
        await session.commit()

        poller = FeedPoller()
        result_task = await poller.process_item(feed_item, [wl], session=session)
        assert result_task is None  # Skipped duplicate


@pytest.mark.asyncio
async def test_process_item_failure_handling():
    """Verify process_item records failure status when resolution fails."""
    feed_item = FeedItem(
        title="Failing App v1.0.0 [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=555",
    )

    async for session in get_db():
        wl = WatchlistItem(app_name="Failing App", enabled=True)
        session.add(wl)
        await session.commit()
        await session.refresh(wl)

        poller = FeedPoller()
        with patch.object(
            poller.resolver_manager,
            "resolve",
            new_callable=AsyncMock,
            side_effect=Exception("All hoster mirrors dead"),
        ), patch.object(
            poller.notification_service,
            "notify_download_failed",
            new_callable=AsyncMock,
        ) as mock_fail_notif:
            task = await poller.process_item(feed_item, [wl], session=session)
            assert task is not None
            assert task.status == "failed"
            assert "All hoster mirrors dead" in (task.error_message or "")
            assert mock_fail_notif.called


@pytest.mark.asyncio
async def test_process_item_archive_extraction(tmp_path):
    """Verify process_item unpacks archive files and organizes extracted APK."""
    feed_item = FeedItem(
        title="Zipped App v2.5.0 [derrin]",
        link="https://forum.mobilism.org/viewtopic.php?t=777",
    )

    archive_file = tmp_path / "Zipped_App.zip"
    archive_file.write_bytes(b"dummy zip data")

    extracted_apk = tmp_path / "Zipped App v2.5.0 [derrin].apk"
    extracted_apk.write_bytes(b"extracted apk data")

    async for session in get_db():
        wl = WatchlistItem(app_name="Zipped App", enabled=True)
        session.add(wl)
        await session.commit()
        await session.refresh(wl)

        poller = FeedPoller()
        with patch.object(
            poller.resolver_manager,
            "resolve",
            new_callable=AsyncMock,
            return_value=ResolvedDownload(
                download_url="https://real-debrid.com/d/zip123",
                original_link="https://forum.mobilism.org/viewtopic.php?t=777",
                filename="Zipped_App.zip",
                tier="real_debrid",
            ),
        ), patch.object(
            poller.download_engine,
            "download",
            new_callable=AsyncMock,
            return_value=archive_file,
        ), patch.object(
            poller.archive_extractor,
            "is_archive",
            return_value=True,
        ), patch.object(
            poller.archive_extractor,
            "extract",
            return_value=[extracted_apk],
        ), patch.object(
            poller.nextcloud_client,
            "trigger_occ_scan",
            new_callable=AsyncMock,
        ), patch.object(
            poller.notification_service,
            "notify_download_completed",
            new_callable=AsyncMock,
        ) as mock_done_notif:
            task = await poller.process_item(feed_item, [wl], session=session)
            assert task is not None
            assert task.status == "completed"
            assert mock_done_notif.called


@pytest.mark.asyncio
async def test_poll_feed_with_remote_url_error():
    """Verify that remote HTTP error during feed fetching is handled gracefully."""
    async for session in get_db():
        feed = FeedSource(
            name="Broken HTTP Feed",
            url="http://non-existent-broken-domain.local/feed.xml",
            enabled=True,
        )
        session.add(feed)
        await session.commit()
        await session.refresh(feed)
        feed_id = feed.id

    poller = FeedPoller()
    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        res = await poller.poll_single_feed(feed_id)
        assert res["polled_feeds"] == 1
        assert res["items_checked"] == 0
        assert "error" in res or res["status"] in ("error", "ok")
