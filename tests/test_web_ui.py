"""Unit and integration tests for Web UI routing, React SPA serving, and legacy fallback."""

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
async def test_spa_root_page(client):
    """Verify GET / returns React SPA index.html."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_watchlist_page(client):
    """Verify GET /watchlist fallback routes to React SPA index.html."""
    resp = await client.get("/watchlist")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_feeds_page(client):
    """Verify GET /feeds fallback routes to React SPA index.html."""
    resp = await client.get("/feeds")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_history_page(client):
    """Verify GET /history fallback routes to React SPA index.html."""
    resp = await client.get("/history")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_settings_page(client):
    """Verify GET /settings fallback routes to React SPA index.html."""
    resp = await client.get("/settings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_arbitrary_client_route(client):
    """Verify arbitrary client-side navigation paths fallback to React SPA index.html."""
    for path in ["/downloads/123", "/watchlist/new", "/custom/nested/path"]:
        resp = await client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_static_assets_serving(client):
    """Verify Vite compiled static assets under /assets are served correctly."""
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        asset_files = list(assets_dir.glob("*.js")) + list(assets_dir.glob("*.css"))
        assert len(asset_files) > 0
        asset_filename = asset_files[0].name
        resp = await client.get(f"/assets/{asset_filename}")
        assert resp.status_code == 200
        assert len(resp.text) > 0


@pytest.mark.asyncio
async def test_spa_direct_file_serving(client):
    """Verify static files in dist root (like index.html) are served directly."""
    resp = await client.get("/index.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_spa_reserved_api_routes_404(client):
    """Verify reserved API/docs/health prefixes return 404 rather than SPA index.html."""
    for path in ["/api/nonexistent", "/health/sub", "/mcp/nonexistent", "/docs/extra", "/openapi.json/sub"]:
        resp = await client.get(path)
        assert resp.status_code == 404
        assert resp.text == "Not found" or "detail" in resp.text


@pytest.mark.asyncio
async def test_spa_assets_not_found(client):
    """Verify non-existent asset under /assets returns 404."""
    resp = await client.get("/assets/non_existent_file_999.js")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_legacy_fallback_when_dist_missing():
    """Verify fallback to Jinja2 templates when frontend/dist is missing."""
    original_exists = Path.exists

    def mock_exists(self):
        # Simulate absence of frontend/dist directory
        path_str = str(self)
        if "frontend" in path_str or "/app/frontend/dist" in path_str:
            return False
        return original_exists(self)

    with patch.object(Path, "exists", mock_exists):
        legacy_app = create_app()
        transport = ASGITransport(app=legacy_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            for path in ["/", "/watchlist", "/feeds", "/history", "/settings"]:
                resp = await c.get(path)
                assert resp.status_code == 200
                assert "text/html" in resp.headers.get("content-type", "")
                assert "APKPipe" in resp.text


@pytest.mark.asyncio
async def test_legacy_static_files():
    """Verify legacy static file serving when fallback mode is active."""
    original_exists = Path.exists

    def mock_exists(self):
        path_str = str(self)
        if "frontend" in path_str or "/app/frontend/dist" in path_str:
            return False
        return original_exists(self)

    with patch.object(Path, "exists", mock_exists):
        legacy_app = create_app()
        transport = ASGITransport(app=legacy_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp_css = await c.get("/static/styles.css")
            assert resp_css.status_code == 200
            assert "css" in resp_css.headers.get("content-type", "")

            resp_js = await c.get("/static/app.js")
            assert resp_js.status_code == 200

            resp_nf = await c.get("/static/nonexistent_file_123.xyz")
            assert resp_nf.status_code == 404


@pytest.mark.asyncio
async def test_app_creation_without_any_dirs():
    """Verify app creation succeeds even if no frontend dist, static, or template dirs exist."""
    with patch.object(Path, "exists", return_value=False):
        empty_app = create_app()
        assert empty_app is not None
