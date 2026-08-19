"""Unit and integration tests for Web UI templates and static file routing."""

from pathlib import Path
from unittest.mock import patch
import pytest
from httpx import ASGITransport, AsyncClient

from apkpipe.database.db import close_db, init_db
from apkpipe.main import create_app


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
    """Async HTTP client for testing FastAPI Web UI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_dashboard_index_route(client):
    """Verify GET / renders index.html dashboard with overview components."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "APKPipe" in html
    assert "Dashboard" in html
    assert "Active Watchlist" in html
    assert "Active Feeds" in html
    assert "Manual Download" in html
    assert "Recent Ingests" in html or "Recent Activity" in html
    assert "Manual Download Trigger" in html


@pytest.mark.asyncio
async def test_watchlist_page_route(client):
    """Verify GET /watchlist renders watchlist.html management view."""
    response = await client.get("/watchlist")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "APKPipe" in html
    assert "Watchlist" in html
    assert "Add Application" in html
    assert "Package Name" in html
    assert "Min Version" in html
    assert "Releaser Whitelist" in html
    assert "Releaser Blacklist" in html


@pytest.mark.asyncio
async def test_feeds_page_route(client):
    """Verify GET /feeds renders feeds.html RSS feed management view."""
    response = await client.get("/feeds")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "APKPipe" in html
    assert "Feeds" in html
    assert "Add Feed" in html
    assert "Poll All Feeds Now" in html
    assert "mobilism_rss" in html


@pytest.mark.asyncio
async def test_history_page_route(client):
    """Verify GET /history renders history.html queue and audit view."""
    response = await client.get("/history")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "APKPipe" in html
    assert "Download Queue & Audit History" in html
    assert "Active Queue" in html
    assert "Completed History" in html
    assert "Live Poll" in html


@pytest.mark.asyncio
async def test_settings_page_route(client):
    """Verify GET /settings renders settings.html configuration editor."""
    response = await client.get("/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "APKPipe" in html
    assert "Settings" in html
    assert "Real-Debrid Tier 1 Resolver" in html
    assert "JDownloader Tier 2 Fallback" in html
    assert "Nextcloud" in html
    assert "Notifications" in html


@pytest.mark.asyncio
async def test_static_css_serving(client):
    """Verify GET /static/styles.css serves the stylesheet."""
    response = await client.get("/static/styles.css")
    assert response.status_code == 200
    assert "css" in response.headers.get("content-type", "")
    css = response.text
    assert len(css) > 0
    assert "--bg-main" in css or ".badge" in css or ".glass-panel" in css


@pytest.mark.asyncio
async def test_static_js_serving(client):
    """Verify GET /static/app.js serves Alpine.js application logic."""
    response = await client.get("/static/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "") or "text/plain" in response.headers.get("content-type", "")
    js = response.text
    assert "dashboardApp" in js
    assert "watchlistApp" in js
    assert "feedsApp" in js
    assert "historyApp" in js
    assert "settingsApp" in js
    assert "formatBytes" in js
    assert "showToast" in js


@pytest.mark.asyncio
async def test_static_file_not_found(client):
    """Verify non-existent static file returns 404."""
    response = await client.get("/static/non_existent_file_123.xyz")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_navigation_active_states(client):
    """Verify active navigation links are marked correctly across pages."""
    pages = ["/", "/watchlist", "/feeds", "/history", "/settings"]
    for path in pages:
        res = await client.get(path)
        assert res.status_code == 200
        assert "APKPipe" in res.text
        assert "bg-indigo-600/20" in res.text or "border-indigo-500" in res.text


@pytest.mark.asyncio
async def test_app_creation_without_static_dir():
    """Verify app creation handles missing static directory without crashing."""
    with patch("pathlib.Path.exists", return_value=False):
        app = create_app()
        assert app is not None
