"""Unit and integration tests for FastAPI REST routes, Lifespan, and MCP router."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from apkpipe.database.db import close_db, get_db, init_db
from apkpipe.database.models import (
    AppSetting,
    DownloadHistory,
    DownloadTask,
    FeedSource,
    WatchlistItem,
)
from apkpipe.main import create_app
from apkpipe.resolvers.base import ResolvedDownload


@pytest.fixture(autouse=True)
async def setup_test_database():
    """Setup and teardown in-memory test database for each test."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    engine = await init_db(test_db_url)
    yield engine
    await close_db()


@pytest.fixture
def app():
    """Create test application instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP client for testing FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# =========================================================================
# Health & Root Routes
# =========================================================================

@pytest.mark.asyncio
async def test_health_check_endpoint(client):
    """Verify GET /health returns 200 and health info."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data


# =========================================================================
# Watchlist REST Endpoints (/api/watchlist)
# =========================================================================

@pytest.mark.asyncio
async def test_watchlist_crud_lifecycle(client):
    """Test full CRUD cycle for /api/watchlist."""
    # 1. Initially empty
    list_resp = await client.get("/api/watchlist")
    assert list_resp.status_code == 200
    assert list_resp.json() == []

    # 2. Create item
    payload = {
        "app_name": "Spotify",
        "package_name": "com.spotify.music",
        "title_regex": r"^Spotify.*\[Premium\].*",
        "min_version": "8.9.0",
        "releaser_whitelist": ["Balatan", "derrin"],
        "releaser_blacklist": ["spammer"],
        "enabled": True,
        "category": "Music & Audio",
    }
    create_resp = await client.post("/api/watchlist", json=payload)
    assert create_resp.status_code == 201
    created_data = create_resp.json()
    item_id = created_data["id"]
    assert created_data["app_name"] == "Spotify"
    assert created_data["package_name"] == "com.spotify.music"
    assert created_data["releaser_whitelist"] == ["Balatan", "derrin"]

    # 3. Get single item
    get_resp = await client.get(f"/api/watchlist/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == item_id

    # 4. Get non-existent
    not_found_resp = await client.get("/api/watchlist/99999")
    assert not_found_resp.status_code == 404

    # 5. Update item
    update_payload = {
        "min_version": "8.9.10",
        "category": "Audio",
        "enabled": False,
    }
    put_resp = await client.put(f"/api/watchlist/{item_id}", json=update_payload)
    assert put_resp.status_code == 200
    updated_data = put_resp.json()
    assert updated_data["min_version"] == "8.9.10"
    assert updated_data["category"] == "Audio"
    assert updated_data["enabled"] is False

    # 6. Update non-existent
    put_nf_resp = await client.put("/api/watchlist/99999", json=update_payload)
    assert put_nf_resp.status_code == 404

    # 7. List with filters
    # Add a second item
    await client.post(
        "/api/watchlist",
        json={"app_name": "Nova Launcher", "category": "Personalization", "enabled": True},
    )

    # Filter enabled=True
    filt_resp = await client.get("/api/watchlist?enabled=true")
    assert filt_resp.status_code == 200
    items = filt_resp.json()
    assert len(items) == 1
    assert items[0]["app_name"] == "Nova Launcher"

    # Filter category
    cat_resp = await client.get("/api/watchlist?category=Audio")
    assert cat_resp.status_code == 200
    assert len(cat_resp.json()) == 1

    # Filter query
    q_resp = await client.get("/api/watchlist?query=nova")
    assert q_resp.status_code == 200
    assert len(q_resp.json()) == 1

    # 8. Delete item
    del_resp = await client.delete(f"/api/watchlist/{item_id}")
    assert del_resp.status_code == 200

    # Verify deleted
    get_del_resp = await client.get(f"/api/watchlist/{item_id}")
    assert get_del_resp.status_code == 404

    # Delete non-existent
    del_nf_resp = await client.delete(f"/api/watchlist/{item_id}")
    assert del_nf_resp.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_validation_errors(client):
    """Test validation errors for watchlist creation."""
    # Missing required app_name
    resp = await client.post("/api/watchlist", json={"category": "Tools"})
    assert resp.status_code == 422


# =========================================================================
# Feeds REST Endpoints (/api/feeds)
# =========================================================================

@pytest.mark.asyncio
async def test_feeds_crud_and_polling(client, app):
    """Test CRUD and polling triggers for /api/feeds."""
    # 1. Create feed
    feed_payload = {
        "name": "Mobilism Releases",
        "url": "https://forum.mobilism.org/feed.php?f=398",
        "feed_type": "mobilism_rss",
        "enabled": True,
        "poll_interval_minutes": 15,
    }
    create_resp = await client.post("/api/feeds", json=feed_payload)
    assert create_resp.status_code == 201
    feed_data = create_resp.json()
    feed_id = feed_data["id"]
    assert feed_data["name"] == "Mobilism Releases"

    # 2. Get single feed
    get_resp = await client.get(f"/api/feeds/{feed_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == feed_id

    # 3. List feeds
    list_resp = await client.get("/api/feeds")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Update feed
    update_resp = await client.put(
        f"/api/feeds/{feed_id}",
        json={"name": "Mobilism Updated", "poll_interval_minutes": 30},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Mobilism Updated"
    assert update_resp.json()["poll_interval_minutes"] == 30

    # 5. Non-existent feed get/put/delete
    assert (await client.get("/api/feeds/9999")).status_code == 404
    assert (await client.put("/api/feeds/9999", json={"name": "x"})).status_code == 404
    assert (await client.delete("/api/feeds/9999")).status_code == 404

    # 6. Poll single feed endpoint
    with patch("apkpipe.feeds.poller.FeedPoller.poll_single_feed", new_callable=AsyncMock) as mock_poll_single:
        mock_poll_single.return_value = {
            "status": "ok",
            "polled_feeds": 1,
            "items_checked": 5,
            "matches_found": 1,
            "tasks_created": 1,
        }
        poll_resp = await client.post(f"/api/feeds/{feed_id}/poll")
        assert poll_resp.status_code == 200
        assert poll_resp.json()["matches_found"] == 1

    # 7. Poll all feeds endpoint
    with patch("apkpipe.feeds.poller.FeedPoller.poll_all_feeds", new_callable=AsyncMock) as mock_poll_all:
        mock_poll_all.return_value = {
            "status": "ok",
            "polled_feeds": 1,
            "items_checked": 5,
            "matches_found": 1,
            "tasks_created": 1,
        }
        poll_all_resp = await client.post("/api/feeds/poll-all")
        assert poll_all_resp.status_code == 200
        assert poll_all_resp.json()["polled_feeds"] == 1

    # 8. Delete feed
    del_resp = await client.delete(f"/api/feeds/{feed_id}")
    assert del_resp.status_code == 200


# =========================================================================
# Downloads REST Endpoints (/api/downloads)
# =========================================================================

@pytest.mark.asyncio
async def test_downloads_queue_and_history(client):
    """Test /api/downloads/queue and /api/downloads/history."""
    # Insert dummy task and history
    async for session in get_db():
        task = DownloadTask(
            feed_item_title="Nova Launcher v8.0.18 [Balatan]",
            feed_item_url="https://rapidgator.net/file/123",
            matched_version="8.0.18",
            matched_releaser="Balatan",
            status="pending",
        )
        history = DownloadHistory(
            app_name="Spotify",
            version="8.9.0",
            releaser="Balatan",
            target_path="/data/downloads/Spotify/Spotify v8.9.0.apk",
            file_size=50000000,
            duration_seconds=5.2,
            download_tier="real_debrid",
            status="completed",
        )
        session.add_all([task, history])
        await session.commit()

    # Query queue
    q_resp = await client.get("/api/downloads/queue")
    assert q_resp.status_code == 200
    queue = q_resp.json()
    assert len(queue) == 1
    assert queue[0]["status"] == "pending"

    # Query history
    h_resp = await client.get("/api/downloads/history")
    assert h_resp.status_code == 200
    history_items = h_resp.json()
    assert len(history_items) == 1
    assert history_items[0]["app_name"] == "Spotify"


@pytest.mark.asyncio
async def test_manual_download_and_retry_and_delete(client, tmp_path):
    """Test manual submission, retry, and deletion of download tasks."""
    # 1. Manual download with auto_resolve=False
    manual_resp = await client.post(
        "/api/downloads/manual",
        json={
            "url": "https://rapidgator.net/file/12345/app.apk",
            "app_name": "TestManualApp",
            "version": "1.2.3",
            "releaser": "derrin",
            "auto_resolve": False,
        },
    )
    assert manual_resp.status_code == 201
    task_data = manual_resp.json()
    task_id = task_data["id"]
    assert task_data["status"] == "pending"

    # 2. Retry task
    dummy_apk = tmp_path / "app.apk"
    dummy_apk.write_bytes(b"dummy apk content")

    with patch(
        "apkpipe.resolvers.manager.ResolverManager.resolve",
        new_callable=AsyncMock,
        return_value=ResolvedDownload(
            download_url="https://real-debrid.com/d/abc",
            original_link="https://rapidgator.net/file/12345/app.apk",
            filename="TestManualApp v1.2.3.apk",
            tier="real_debrid",
        ),
    ), patch(
        "apkpipe.downloader.engine.DownloadEngine.download",
        new_callable=AsyncMock,
        return_value=dummy_apk,
    ), patch(
        "apkpipe.integrations.nextcloud.NextcloudClient.trigger_occ_scan",
        new_callable=AsyncMock,
    ):
        retry_resp = await client.post(f"/api/downloads/{task_id}/retry")
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] in ("completed", "pending", "downloading")

    # Retry non-existent task
    assert (await client.post("/api/downloads/99999/retry")).status_code == 404

    # 3. Delete task
    del_resp = await client.delete(f"/api/downloads/{task_id}")
    assert del_resp.status_code == 200

    # Delete non-existent task
    assert (await client.delete(f"/api/downloads/{task_id}")).status_code == 404


# =========================================================================
# Settings REST Endpoints (/api/settings)
# =========================================================================

@pytest.mark.asyncio
async def test_settings_get_and_post(client):
    """Test getting and updating application settings via REST."""
    # 1. GET /api/settings
    get_resp = await client.get("/api/settings")
    assert get_resp.status_code == 200
    settings_data = get_resp.json()
    assert "app_name" in settings_data
    assert "database_url" in settings_data
    assert "poll_interval_seconds" in settings_data
    assert "alldebrid_api_key" in settings_data
    assert "alldebrid_agent" in settings_data

    # 2. POST /api/settings
    update_payload = {
        "real_debrid_api_token": "secret_token_123",
        "alldebrid_api_key": "alldebrid_api_key_789",
        "alldebrid_agent": "apkpipe_custom",
        "nextcloud_url": "https://nextcloud.homelab.local",
        "poll_interval_seconds": 600,
        "ntfy_topic": "homelab-apks",
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200
    updated_data = post_resp.json()
    assert updated_data["poll_interval_seconds"] == 600
    assert updated_data["nextcloud_url"] == "https://nextcloud.homelab.local"
    assert updated_data["alldebrid_api_key"] == "alldebrid_api_key_789"
    assert updated_data["alldebrid_agent"] == "apkpipe_custom"

    # Verify settings persisted in DB
    async for session in get_db():
        st = (await session.execute(select(AppSetting).where(AppSetting.key == "ntfy_topic"))).scalar_one_or_none()
        assert st is not None
        assert st.value == "homelab-apks"

        st_ad = (await session.execute(select(AppSetting).where(AppSetting.key == "alldebrid_api_key"))).scalar_one_or_none()
        assert st_ad is not None
        assert st_ad.value == "alldebrid_api_key_789"

    # 3. PUT /api/settings
    put_payload = {
        "alldebrid_api_key": "updated_ad_key_999",
    }
    put_resp = await client.put("/api/settings", json=put_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["alldebrid_api_key"] == "updated_ad_key_999"


# =========================================================================
# MCP Routes (/mcp)
# =========================================================================

@pytest.mark.asyncio
async def test_mcp_endpoints_mounted(client):
    """Verify MCP protocol endpoints are properly mounted in main app."""
    # POST /mcp ping
    ping_resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
    )
    assert ping_resp.status_code == 200
    assert ping_resp.json()["result"] == {}

    # POST /mcp tools/list
    tools_resp = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert tools_resp.status_code == 200
    assert "tools" in tools_resp.json()["result"]


# =========================================================================
# App Lifespan and CORS
# =========================================================================

@pytest.mark.asyncio
async def test_manual_download_auto_resolve_flow(client, tmp_path):
    """Test manual download with auto_resolve=True end-to-end with mocked downloader."""
    dummy_apk = tmp_path / "AutoApp.apk"
    dummy_apk.write_bytes(b"apk content")

    with patch(
        "apkpipe.resolvers.manager.ResolverManager.resolve",
        new_callable=AsyncMock,
        return_value=ResolvedDownload(
            download_url="https://real-debrid.com/d/abc",
            original_link="https://forum.mobilism.org/viewtopic.php?t=8888",
            filename="AutoApp v1.0.0.apk",
            tier="real_debrid",
        ),
    ), patch(
        "apkpipe.downloader.engine.DownloadEngine.download",
        new_callable=AsyncMock,
        return_value=dummy_apk,
    ), patch(
        "apkpipe.integrations.nextcloud.NextcloudClient.trigger_occ_scan",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/downloads/manual",
            json={
                "url": "https://forum.mobilism.org/viewtopic.php?t=8888",
                "app_name": "AutoApp",
                "version": "1.0.0",
                "releaser": "derrin",
                "auto_resolve": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "completed"
        assert data["file_path"] is not None


@pytest.mark.asyncio
async def test_manual_download_resolution_failure(client):
    """Test manual download error handling when resolution fails."""
    with patch(
        "apkpipe.resolvers.manager.ResolverManager.resolve",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            "/api/downloads/manual",
            json={
                "url": "https://example.com/dead_link.apk",
                "auto_resolve": True,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "failed"
        assert "Failed to resolve" in data["error_message"]


@pytest.mark.asyncio
async def test_downloads_queue_filter_and_search(client):
    """Test downloads queue filtering by status and history searching."""
    async for session in get_db():
        t1 = DownloadTask(feed_item_title="Pending Task", status="pending")
        t2 = DownloadTask(feed_item_title="Failed Task", status="failed")
        h1 = DownloadHistory(app_name="SearchTargetApp", status="completed")
        h2 = DownloadHistory(app_name="OtherApp", status="failed")
        session.add_all([t1, t2, h1, h2])
        await session.commit()

    # Filter queue by status
    q_resp = await client.get("/api/downloads/queue?status=failed")
    assert q_resp.status_code == 200
    q_items = q_resp.json()
    assert len(q_items) == 1
    assert q_items[0]["feed_item_title"] == "Failed Task"

    # Search history by query
    h_search_resp = await client.get("/api/downloads/history?query=SearchTarget")
    assert h_search_resp.status_code == 200
    h_items = h_search_resp.json()
    assert len(h_items) == 1
    assert h_items[0]["app_name"] == "SearchTargetApp"

    # Filter history by status
    h_filt_resp = await client.get("/api/downloads/history?status=failed")
    assert h_filt_resp.status_code == 200
    assert len(h_filt_resp.json()) == 1


@pytest.mark.asyncio
async def test_watchlist_invalid_regex_validation(client):
    """Test invalid title_regex validation on create and update."""
    # Create invalid
    resp_create = await client.post(
        "/api/watchlist",
        json={"app_name": "Test", "title_regex": "[invalid regex("},
    )
    assert resp_create.status_code == 422

    # Create valid
    resp_ok = await client.post(
        "/api/watchlist",
        json={"app_name": "Valid App", "title_regex": r"^Valid.*"},
    )
    assert resp_ok.status_code == 201
    item_id = resp_ok.json()["id"]

    # Update invalid
    resp_up_inv = await client.put(
        f"/api/watchlist/{item_id}",
        json={"title_regex": "[invalid regex("},
    )
    assert resp_up_inv.status_code == 422


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Verify GET / returns Web Dashboard HTML."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_app_lifespan():
    """Verify application lifespan starts and stops poller cleanly."""
    with patch("apkpipe.feeds.poller.FeedPoller.start", new_callable=AsyncMock) as mock_start, patch(
        "apkpipe.feeds.poller.FeedPoller.stop", new_callable=AsyncMock
    ) as mock_stop:
        app = create_app()
        async with app.router.lifespan_context(app):
            assert mock_start.called
            assert hasattr(app.state, "poller")
        assert mock_stop.called

