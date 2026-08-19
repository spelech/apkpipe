"""Unit tests for SQLite database layer, async session lifecycle, and ORM models."""

import datetime
from sqlalchemy import select
import pytest

from apkpipe.database.db import get_db, init_db, close_db, get_engine, normalize_db_url, get_session_factory
from apkpipe.database.models import (
    Base,
    WatchlistItem,
    FeedSource,
    DownloadTask,
    DownloadHistory,
    AppSetting,
)


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup and teardown in-memory test database for each test."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = await init_db(test_db_url)
    yield engine
    await close_db()


@pytest.mark.asyncio
async def test_normalize_db_url():
    """Verify normalize_db_url handles various input formats."""
    assert normalize_db_url(":memory:") == "sqlite+aiosqlite:///:memory:"
    assert normalize_db_url("sqlite+aiosqlite:///custom.db") == "sqlite+aiosqlite:///custom.db"
    assert normalize_db_url("sqlite:///custom.db") == "sqlite+aiosqlite:///custom.db"
    assert normalize_db_url("data/apkpipe.db") == "sqlite+aiosqlite:///data/apkpipe.db"


@pytest.mark.asyncio
async def test_get_session_factory_custom_engine():
    """Verify get_session_factory works with custom engine parameter."""
    engine = get_engine("sqlite+aiosqlite:///:memory:")
    factory = get_session_factory(engine)
    async with factory() as session:
        assert session.is_active


@pytest.mark.asyncio
async def test_get_session_factory_default():
    """Verify get_session_factory initializes engine if not present."""
    await close_db()
    factory = get_session_factory()
    assert factory is not None
    await close_db()


@pytest.mark.asyncio
async def test_init_db_creates_all_tables(setup_test_database):
    """Verify that init_db creates all required tables in SQLite."""
    engine = setup_test_database
    async with engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: sync_conn.dialect.get_table_names(sync_conn)
        )
        assert "watchlist_items" in tables
        assert "feed_sources" in tables
        assert "download_tasks" in tables
        assert "download_history" in tables
        assert "app_settings" in tables


@pytest.mark.asyncio
async def test_get_db_session_lifecycle():
    """Verify get_db yields an active AsyncSession."""
    async for session in get_db():
        assert session.is_active
        result = await session.execute(select(1))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_watchlist_item_crud():
    """Verify CRUD operations and default values for WatchlistItem."""
    async for session in get_db():
        item = WatchlistItem(
            app_name="Nova Launcher",
            package_name="com.teslacoilsw.launcher",
            title_regex=r"^Nova Launcher Prime.*",
            min_version="8.0.0",
            releaser_whitelist=["Balatan", "derrin"],
            releaser_blacklist=["spammer"],
            category="Personalization",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

        assert item.id is not None
        assert item.app_name == "Nova Launcher"
        assert item.package_name == "com.teslacoilsw.launcher"
        assert item.title_regex == r"^Nova Launcher Prime.*"
        assert item.min_version == "8.0.0"
        assert item.releaser_whitelist == ["Balatan", "derrin"]
        assert item.releaser_blacklist == ["spammer"]
        assert item.enabled is True
        assert item.category == "Personalization"
        assert isinstance(item.created_at, datetime.datetime)
        assert isinstance(item.updated_at, datetime.datetime)

        # Update
        item.min_version = "8.1.0"
        item.enabled = False
        await session.commit()
        await session.refresh(item)
        assert item.min_version == "8.1.0"
        assert item.enabled is False

        # Delete
        await session.delete(item)
        await session.commit()
        res = await session.execute(select(WatchlistItem).where(WatchlistItem.id == item.id))
        assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_watchlist_item_defaults():
    """Verify WatchlistItem default field values."""
    async for session in get_db():
        item = WatchlistItem(app_name="SimpleApp")
        session.add(item)
        await session.commit()
        await session.refresh(item)

        assert item.min_version == "0.0.0"
        assert item.releaser_whitelist == []
        assert item.releaser_blacklist == []
        assert item.enabled is True
        assert item.category == "Apps"


@pytest.mark.asyncio
async def test_feed_source_crud():
    """Verify CRUD operations and default values for FeedSource."""
    async for session in get_db():
        feed = FeedSource(
            name="Mobilism Android Apps",
            url="https://forum.mobilism.org/feed.php?f=398",
            feed_type="mobilism_rss",
            poll_interval_minutes=30,
        )
        session.add(feed)
        await session.commit()
        await session.refresh(feed)

        assert feed.id is not None
        assert feed.name == "Mobilism Android Apps"
        assert feed.url == "https://forum.mobilism.org/feed.php?f=398"
        assert feed.feed_type == "mobilism_rss"
        assert feed.enabled is True
        assert feed.poll_interval_minutes == 30
        assert feed.last_polled_at is None
        assert isinstance(feed.created_at, datetime.datetime)

        # Update last_polled_at
        now = datetime.datetime.now(datetime.timezone.utc)
        feed.last_polled_at = now
        await session.commit()
        await session.refresh(feed)
        assert feed.last_polled_at is not None

        # Delete
        await session.delete(feed)
        await session.commit()
        res = await session.execute(select(FeedSource).where(FeedSource.id == feed.id))
        assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_download_task_crud_and_relationship():
    """Verify CRUD and relationships for DownloadTask and WatchlistItem."""
    async for session in get_db():
        item = WatchlistItem(app_name="SD Maid Pro")
        session.add(item)
        await session.commit()
        await session.refresh(item)

        task = DownloadTask(
            watchlist_item=item,
            feed_item_title="SD Maid Pro v5.5.9 [Balatan]",
            feed_item_url="https://forum.mobilism.org/viewtopic.php?t=12345",
            matched_version="5.5.9",
            matched_releaser="Balatan",
            status="pending",
            mirror_urls=["https://rapidgator.net/file/1", "https://uploady.io/2"],
            resolved_url="https://real-debrid.com/d/abc",
            download_tier="real_debrid",
            file_path="/data/downloads/SD Maid Pro/SD Maid Pro v5.5.9 [Balatan].apk",
            file_size=12345678,
            error_message=None,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        await session.refresh(item)

        assert task.id is not None
        assert task.watchlist_item_id == item.id
        assert task.feed_item_title == "SD Maid Pro v5.5.9 [Balatan]"
        assert task.matched_version == "5.5.9"
        assert task.matched_releaser == "Balatan"
        assert task.status == "pending"
        assert task.mirror_urls == ["https://rapidgator.net/file/1", "https://uploady.io/2"]
        assert task.download_tier == "real_debrid"
        assert task.file_size == 12345678
        assert task.watchlist_item.app_name == "SD Maid Pro"
        assert len(item.tasks) == 1
        assert item.tasks[0].id == task.id

        # Update status
        task.status = "completed"
        task.completed_at = datetime.datetime.now(datetime.timezone.utc)
        await session.commit()
        await session.refresh(task)
        assert task.status == "completed"
        assert task.completed_at is not None


@pytest.mark.asyncio
async def test_download_history_crud_and_relationship():
    """Verify CRUD and relationships for DownloadHistory and DownloadTask."""
    async for session in get_db():
        task = DownloadTask(
            feed_item_title="VLC for Android v3.5.4 [derrin]",
            status="completed",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        history = DownloadHistory(
            task=task,
            app_name="VLC",
            version="3.5.4",
            releaser="derrin",
            target_path="/data/downloads/VLC/VLC v3.5.4 [derrin].apk",
            file_size=35000000,
            duration_seconds=12.4,
            download_tier="real_debrid",
            status="completed",
        )
        session.add(history)
        await session.commit()
        await session.refresh(history)
        await session.refresh(task)

        assert history.id is not None
        assert history.task_id == task.id
        assert history.app_name == "VLC"
        assert history.version == "3.5.4"
        assert history.releaser == "derrin"
        assert history.file_size == 35000000
        assert history.duration_seconds == 12.4
        assert history.download_tier == "real_debrid"
        assert history.status == "completed"
        assert isinstance(history.downloaded_at, datetime.datetime)
        assert history.task.feed_item_title == "VLC for Android v3.5.4 [derrin]"
        assert task.history.id == history.id


@pytest.mark.asyncio
async def test_app_setting_crud():
    """Verify CRUD operations on AppSetting."""
    async for session in get_db():
        setting = AppSetting(
            key="theme",
            value="dark",
            description="Web Dashboard Theme preference",
        )
        session.add(setting)
        await session.commit()
        await session.refresh(setting)

        assert setting.key == "theme"
        assert setting.value == "dark"
        assert setting.description == "Web Dashboard Theme preference"
        assert isinstance(setting.updated_at, datetime.datetime)

        # Update
        setting.value = "light"
        await session.commit()
        await session.refresh(setting)
        assert setting.value == "light"

        # Delete
        await session.delete(setting)
        await session.commit()
        res = await session.execute(select(AppSetting).where(AppSetting.key == "theme"))
        assert res.scalar_one_or_none() is None
