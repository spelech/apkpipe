"""Unit tests for Tiered Resolution Engine (Real-Debrid and JDownloader 2)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from apkpipe.resolvers.base import (
    AuthenticationError,
    BaseResolver,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    ResolverError,
    UnsupportedHosterError,
)
from apkpipe.resolvers.direct import DirectResolver
from apkpipe.resolvers.jdownloader import JDownloaderResolver
from apkpipe.resolvers.manager import ResolutionManager
from apkpipe.resolvers.real_debrid import RealDebridResolver


# ---------------------------------------------------------------------------
# 1. Base Dataclass & Abstract Resolver Tests
# ---------------------------------------------------------------------------


def test_resolved_download_dataclass():
    """Test ResolvedDownload dataclass instantiation and fields."""
    resolved = ResolvedDownload(
        download_url="https://download.real-debrid.com/d/123/app.apk",
        filename="app_v1.0.apk",
        filesize=50000000,
        hoster="rapidgator.net",
        tier="real_debrid",
        original_link="https://rapidgator.net/file/123/app.apk.html",
        metadata={"chunks": 4, "id": "123"},
    )
    assert resolved.download_url == "https://download.real-debrid.com/d/123/app.apk"
    assert resolved.filename == "app_v1.0.apk"
    assert resolved.filesize == 50000000
    assert resolved.hoster == "rapidgator.net"
    assert resolved.tier == "real_debrid"
    assert resolved.original_link == "https://rapidgator.net/file/123/app.apk.html"
    assert resolved.metadata["id"] == "123"


def test_resolved_download_defaults():
    """Test ResolvedDownload default values."""
    resolved = ResolvedDownload(
        download_url="https://example.com/app.apk",
        original_link="https://example.com/app.apk",
        tier="direct",
    )
    assert resolved.download_url == "https://example.com/app.apk"
    assert resolved.filename == ""
    assert resolved.filesize == 0
    assert resolved.hoster == ""
    assert resolved.tier == "direct"
    assert resolved.original_link == "https://example.com/app.apk"
    assert resolved.metadata == {}


def test_base_resolver_abstract_enforcement():
    """Test that BaseResolver cannot be instantiated without implementing abstract methods."""
    class IncompleteResolver(BaseResolver):
        pass

    with pytest.raises(TypeError):
        IncompleteResolver()


# ---------------------------------------------------------------------------
# 2. Real-Debrid Resolver Tests
# ---------------------------------------------------------------------------


def test_real_debrid_init():
    """Test RealDebridResolver initialization with explicit token and fallback to settings."""
    resolver = RealDebridResolver(api_token="my_token_123", timeout=20.0)
    assert resolver.api_token == "my_token_123"
    assert resolver.timeout == 20.0
    assert resolver.base_url == "https://api.real-debrid.com/rest/1.0"
    assert resolver.is_configured is True

    with patch("apkpipe.resolvers.real_debrid.get_settings") as mock_settings:
        mock_settings.return_value.real_debrid_api_token = "env_token_456"
        resolver_env = RealDebridResolver()
        assert resolver_env.api_token == "env_token_456"
        assert resolver_env.is_configured is True

    with patch("apkpipe.resolvers.real_debrid.get_settings") as mock_settings:
        mock_settings.return_value.real_debrid_api_token = ""
        resolver_unconfigured = RealDebridResolver()
        assert resolver_unconfigured.api_token == ""
        assert resolver_unconfigured.is_configured is False


@pytest.mark.asyncio
async def test_real_debrid_can_resolve():
    """Test RealDebridResolver can_resolve logic."""
    resolver = RealDebridResolver(api_token="valid_token")

    # Common RD supported hosters
    assert await resolver.can_resolve("https://rapidgator.net/file/123/test.apk.html") is True
    assert await resolver.can_resolve("https://rg.to/file/123/test.apk.html") is True
    assert await resolver.can_resolve("https://mega.nz/file/xyz#123") is True
    assert await resolver.can_resolve("https://katfile.com/abc/test.apk") is True
    assert await resolver.can_resolve("https://dropgalaxy.in/drive/xyz") is True
    assert await resolver.can_resolve("https://uploady.io/file/123") is True
    assert await resolver.can_resolve("https://1fichier.com/?abcdef") is True

    # Non-supported / junk links
    assert await resolver.can_resolve("https://unknown-file-hoster-xyz.biz/123") is False
    assert await resolver.can_resolve("not a url") is False
    assert await resolver.can_resolve("") is False

    # Unconfigured resolver returns False
    unconf_resolver = RealDebridResolver(api_token="")
    assert await unconf_resolver.can_resolve("https://rapidgator.net/file/123/test.apk.html") is False


@pytest.mark.asyncio
async def test_real_debrid_get_supported_hosts():
    """Test get_supported_hosts fetches list from /hosts/status."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rapidgator.net": {"status": "up", "check_time": 123},
        "mega.nz": {"status": "up", "check_time": 123},
        "deadhost.com": {"status": "down", "check_time": 123},
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    hosts = await resolver.get_supported_hosts(client=mock_client)

    assert "rapidgator.net" in hosts
    assert "mega.nz" in hosts
    assert "deadhost.com" not in hosts
    mock_client.get.assert_awaited_once_with(
        "https://api.real-debrid.com/rest/1.0/hosts/status",
        headers={"Authorization": "Bearer valid_token"},
    )


@pytest.mark.asyncio
async def test_real_debrid_check_link():
    """Test check_link sends POST to /unrestrict/check."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "host": "rapidgator.net",
        "link": "https://rapidgator.net/file/123",
        "filename": "Nova_Launcher.apk",
        "filesize": 12345678,
        "supported": 1,
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    result = await resolver.check_link("https://rapidgator.net/file/123", client=mock_client)

    assert result["supported"] == 1
    assert result["filename"] == "Nova_Launcher.apk"
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_debrid_resolve_success():
    """Test successful link unrestrict via RealDebridResolver."""
    mock_payload = {
        "id": "UNRESTRICTED123",
        "filename": "Nova_Launcher_v8.0.18.apk",
        "mimeType": "application/vnd.android.package-archive",
        "filesize": 25000000,
        "link": "https://rapidgator.net/file/abc/Nova_Launcher_v8.0.18.apk.html",
        "host": "rapidgator.net",
        "chunks": 4,
        "crc": 0,
        "download": "https://download.real-debrid.com/d/UNRESTRICTED123/Nova_Launcher_v8.0.18.apk",
        "streamable": 0,
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    resolved = await resolver.resolve(
        "https://rapidgator.net/file/abc/Nova_Launcher_v8.0.18.apk.html",
        password="link_pass_123",
        client=mock_client,
    )

    assert resolved is not None
    assert resolved.download_url == "https://download.real-debrid.com/d/UNRESTRICTED123/Nova_Launcher_v8.0.18.apk"
    assert resolved.filename == "Nova_Launcher_v8.0.18.apk"
    assert resolved.filesize == 25000000
    assert resolved.hoster == "rapidgator.net"
    assert resolved.tier == "real_debrid"
    assert resolved.original_link == "https://rapidgator.net/file/abc/Nova_Launcher_v8.0.18.apk.html"
    assert resolved.metadata["id"] == "UNRESTRICTED123"

    mock_client.post.assert_awaited_once()
    call_args, call_kwargs = mock_client.post.call_args
    assert "unrestrict/link" in call_args[0]
    assert call_kwargs["data"]["link"] == "https://rapidgator.net/file/abc/Nova_Launcher_v8.0.18.apk.html"
    assert call_kwargs["data"]["password"] == "link_pass_123"
    assert call_kwargs["headers"]["Authorization"] == "Bearer valid_token"


@pytest.mark.asyncio
async def test_real_debrid_resolve_unconfigured():
    """Test resolve returns None when RealDebridResolver has no token."""
    resolver = RealDebridResolver(api_token="")
    resolved = await resolver.resolve("https://rapidgator.net/file/123")
    assert resolved is None


@pytest.mark.asyncio
async def test_real_debrid_resolve_internal_client():
    """Test resolve instantiates and closes internal client when client is None."""
    mock_payload = {
        "id": "ID999",
        "filename": "app.apk",
        "filesize": 1000,
        "host": "rg.to",
        "download": "https://download.real-debrid.com/d/ID999/app.apk",
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("apkpipe.resolvers.real_debrid.httpx.AsyncClient", return_value=mock_client):
        resolver = RealDebridResolver(api_token="valid_token")
        resolved = await resolver.resolve("https://rg.to/file/123")
        assert resolved is not None
        assert resolved.download_url == "https://download.real-debrid.com/d/ID999/app.apk"
        mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_debrid_resolve_auth_error():
    """Test RealDebridResolver raises AuthenticationError on 401/403 or bad_token."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": "bad_token", "error_code": 8}
    mock_resp.text = '{"error": "bad_token", "error_code": 8}'

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="invalid_token")
    with pytest.raises(AuthenticationError, match="bad_token"):
        await resolver.resolve("https://rapidgator.net/file/123", client=mock_client)


@pytest.mark.asyncio
async def test_real_debrid_resolve_rate_limit():
    """Test RealDebridResolver raises RateLimitError on 429 or rate limit error code."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.json.return_value = {"error": "rate_limit_exceeded", "error_code": 35}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    with pytest.raises(RateLimitError, match="(?i)rate limit"):
        await resolver.resolve("https://rapidgator.net/file/123", client=mock_client)


@pytest.mark.asyncio
async def test_real_debrid_resolve_unsupported_hoster():
    """Test RealDebridResolver raises UnsupportedHosterError on hoster error codes."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"error": "host_not_supported", "error_code": 16}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    with pytest.raises(UnsupportedHosterError, match="host_not_supported"):
        await resolver.resolve("https://unsupported.com/file/123", client=mock_client)


@pytest.mark.asyncio
async def test_real_debrid_resolve_dead_link():
    """Test RealDebridResolver raises LinkDeadError when file is deleted or link is dead."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"error": "file_not_found", "error_code": 22}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = RealDebridResolver(api_token="valid_token")
    with pytest.raises(LinkDeadError, match="file_not_found"):
        await resolver.resolve("https://rapidgator.net/file/deleted", client=mock_client)


@pytest.mark.asyncio
async def test_real_debrid_resolve_network_error():
    """Test RealDebridResolver raises ResolverError on network connection failure."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.ConnectError("Network timeout")

    resolver = RealDebridResolver(api_token="valid_token")
    with pytest.raises(ResolverError, match="Network timeout"):
        await resolver.resolve("https://rapidgator.net/file/123", client=mock_client)


# ---------------------------------------------------------------------------
# 3. JDownloader 2 Resolver Tests
# ---------------------------------------------------------------------------


def test_jdownloader_init(tmp_path: Path):
    """Test JDownloaderResolver initialization with watch_dir and credentials."""
    resolver = JDownloaderResolver(
        watch_dir=str(tmp_path),
        email="jd@example.com",
        password="secret_password",
        device_name="MyNAS",
    )
    assert resolver.watch_dir == Path(tmp_path)
    assert resolver.email == "jd@example.com"
    assert resolver.password == "secret_password"
    assert resolver.device_name == "MyNAS"
    assert resolver.is_configured is True

    # Fallback to settings
    with patch("apkpipe.resolvers.jdownloader.get_settings") as mock_settings:
        mock_settings.return_value.jdownloader_email = "env_jd@example.com"
        mock_settings.return_value.jdownloader_password = "env_password"
        mock_settings.return_value.jdownloader_device_name = "EnvNAS"
        mock_settings.return_value.download_dir = "/data/downloads"
        mock_settings.return_value.staging_dir = "/data/staging"

        resolver_env = JDownloaderResolver()
        assert resolver_env.email == "env_jd@example.com"
        assert resolver_env.is_configured is True

    with patch("apkpipe.resolvers.jdownloader.get_settings") as mock_settings:
        mock_settings.return_value.jdownloader_email = ""
        mock_settings.return_value.jdownloader_password = ""
        mock_settings.return_value.jdownloader_device_name = ""
        mock_settings.return_value.jdownloader_watch_dir = ""

        resolver_unconf = JDownloaderResolver(watch_dir=None)
        assert resolver_unconf.is_configured is False


@pytest.mark.asyncio
async def test_jdownloader_can_resolve(tmp_path: Path):
    """Test JDownloaderResolver can_resolve logic."""
    resolver = JDownloaderResolver(watch_dir=str(tmp_path))
    assert await resolver.can_resolve("https://rapidgator.net/file/123") is True
    assert await resolver.can_resolve("https://dropgalaxy.in/drive/456") is True
    assert await resolver.can_resolve("magnet:?xt=urn:btih:xyz") is True
    assert await resolver.can_resolve("invalid-link") is False
    assert await resolver.can_resolve("") is False

    unconf_resolver = JDownloaderResolver(watch_dir=None, email="", password="")
    assert await unconf_resolver.can_resolve("https://rapidgator.net/file/123") is False


@pytest.mark.asyncio
async def test_jdownloader_resolve_via_watch_dir(tmp_path: Path):
    """Test JDownloaderResolver generates a .crawljob file in the watch directory."""
    resolver = JDownloaderResolver(watch_dir=str(tmp_path))

    resolved = await resolver.resolve(
        link="https://dropgalaxy.in/drive/abc123xyz",
        package_name="Nova_Launcher_v8.0.18",
        download_dir="/data/downloads/Nova",
        filename="Nova_Launcher.apk",
    )

    assert resolved is not None
    assert resolved.download_url == "https://dropgalaxy.in/drive/abc123xyz"
    assert resolved.filename == "Nova_Launcher.apk"
    assert resolved.hoster == "dropgalaxy.in"
    assert resolved.tier == "jdownloader"
    assert resolved.original_link == "https://dropgalaxy.in/drive/abc123xyz"
    assert resolved.metadata["method"] == "crawljob"

    # Verify .crawljob file was created on disk
    crawljob_path = Path(resolved.metadata["crawljob_path"])
    assert crawljob_path.exists()
    assert crawljob_path.suffix == ".crawljob"

    content = crawljob_path.read_text()
    assert "text=https://dropgalaxy.in/drive/abc123xyz" in content
    assert "packageName=Nova_Launcher_v8.0.18" in content
    assert "downloadFolder=/data/downloads/Nova" in content
    assert "autoStart=TRUE" in content
    assert "autoConfirm=TRUE" in content
    assert "enabled=TRUE" in content


@pytest.mark.asyncio
async def test_jdownloader_resolve_via_api():
    """Test JDownloaderResolver submits links via MyJDownloader API client."""
    mock_connect_resp = MagicMock(spec=httpx.Response)
    mock_connect_resp.status_code = 200
    mock_connect_resp.json.return_value = {
        "rid": 1,
        "data": {"sessiontoken": "session_token_123"},
    }

    mock_devices_resp = MagicMock(spec=httpx.Response)
    mock_devices_resp.status_code = 200
    mock_devices_resp.json.return_value = {
        "rid": 2,
        "data": {"list": [{"name": "MyNAS", "id": "device_123", "status": "ONLINE"}]},
    }

    mock_add_links_resp = MagicMock(spec=httpx.Response)
    mock_add_links_resp.status_code = 200
    mock_add_links_resp.json.return_value = {
        "rid": 3,
        "data": {"packageId": "pkg_789", "id": 12345},
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [
        mock_connect_resp,
        mock_devices_resp,
        mock_add_links_resp,
    ]

    resolver = JDownloaderResolver(
        email="user@example.com",
        password="secret_password",
        device_name="MyNAS",
        watch_dir=None,
    )

    resolved = await resolver.resolve(
        link="https://uploady.io/file/999",
        package_name="Spotify_Premium",
        download_dir="/data/downloads/Spotify",
        client=mock_client,
    )

    assert resolved is not None
    assert resolved.download_url == "https://uploady.io/file/999"
    assert resolved.filename == "Spotify_Premium"
    assert resolved.hoster == "uploady.io"
    assert resolved.tier == "jdownloader"
    assert resolved.metadata["method"] == "api"
    assert resolved.metadata["device_id"] == "device_123"


@pytest.mark.asyncio
async def test_jdownloader_resolve_unconfigured():
    """Test JDownloaderResolver returns None when neither watch_dir nor credentials exist."""
    resolver = JDownloaderResolver(watch_dir=None, email="", password="")
    resolved = await resolver.resolve("https://dropgalaxy.in/drive/123")
    assert resolved is None


@pytest.mark.asyncio
async def test_jdownloader_resolve_api_auth_failure():
    """Test JDownloaderResolver raises AuthenticationError on API 403 / auth error."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = '{"src": "MYJD", "type": "AUTH_FAILED"}'
    mock_resp.json.return_value = {"src": "MYJD", "type": "AUTH_FAILED"}

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_resp

    resolver = JDownloaderResolver(
        email="bad_user@example.com",
        password="bad_password",
        device_name="MyNAS",
        watch_dir=None,
    )

    with pytest.raises(AuthenticationError, match="AUTH_FAILED"):
        await resolver.resolve("https://uploady.io/file/123", client=mock_client)


# ---------------------------------------------------------------------------
# 4. Direct / Scraper Direct Resolver Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_resolver():
    """Test DirectResolver handles direct file URLs and GitHub releases."""
    resolver = DirectResolver()

    assert await resolver.can_resolve("https://github.com/revanced/app/releases/download/v1.0/app.apk") is True
    assert await resolver.can_resolve("https://example.com/downloads/vlc.apk") is True
    assert await resolver.can_resolve("https://example.com/downloads/bundle.zip") is True
    assert await resolver.can_resolve("https://rapidgator.net/file/123") is False

    resolved = await resolver.resolve("https://github.com/revanced/app/releases/download/v1.0/app.apk")
    assert resolved is not None
    assert resolved.download_url == "https://github.com/revanced/app/releases/download/v1.0/app.apk"
    assert resolved.filename == "app.apk"
    assert resolved.tier == "scraper_direct"
    assert resolved.hoster == "github.com"


# ---------------------------------------------------------------------------
# 5. Resolution Manager (Tiered Orchestration) Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolution_manager_tier1_rd_success():
    """Test ResolutionManager resolves link using Tier 1 (Real-Debrid)."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://download.real-debrid.com/d/123/app.apk",
        filename="app.apk",
        filesize=20000000,
        hoster="rapidgator.net",
        tier="real_debrid",
        original_link="https://rapidgator.net/file/123",
    )

    jd_resolver = AsyncMock(spec=JDownloaderResolver)
    jd_resolver.tier_name = "jdownloader"

    direct_resolver = AsyncMock(spec=DirectResolver)
    direct_resolver.tier_name = "scraper_direct"

    manager = ResolutionManager(
        rd_resolver=rd_resolver,
        jd_resolver=jd_resolver,
        direct_resolver=direct_resolver,
    )

    links = ["https://rapidgator.net/file/123", "https://dropgalaxy.in/drive/456"]
    resolved = await manager.resolve(links)

    assert resolved is not None
    assert resolved.tier == "real_debrid"
    assert resolved.download_url == "https://download.real-debrid.com/d/123/app.apk"
    rd_resolver.resolve.assert_awaited_once()
    jd_resolver.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolution_manager_fallback_to_tier2_jd():
    """Test ResolutionManager falls back to Tier 2 (JDownloader) when Real-Debrid fails."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.side_effect = UnsupportedHosterError("Hoster not supported by RD")

    jd_resolver = AsyncMock(spec=JDownloaderResolver)
    jd_resolver.tier_name = "jdownloader"
    jd_resolver.can_resolve.return_value = True
    jd_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://dropgalaxy.in/drive/456",
        filename="app.apk",
        filesize=0,
        hoster="dropgalaxy.in",
        tier="jdownloader",
        original_link="https://dropgalaxy.in/drive/456",
    )

    direct_resolver = AsyncMock(spec=DirectResolver)
    direct_resolver.tier_name = "scraper_direct"

    manager = ResolutionManager(
        rd_resolver=rd_resolver,
        jd_resolver=jd_resolver,
        direct_resolver=direct_resolver,
    )

    links = ["https://dropgalaxy.in/drive/456"]
    resolved = await manager.resolve(links)

    assert resolved is not None
    assert resolved.tier == "jdownloader"
    assert resolved.download_url == "https://dropgalaxy.in/drive/456"
    rd_resolver.resolve.assert_awaited_once()
    jd_resolver.resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolution_manager_fallback_to_tier3_direct():
    """Test ResolutionManager falls back to Tier 3 (Direct) when RD and JD fail/skip."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    rd_resolver.can_resolve.return_value = False

    jd_resolver = AsyncMock(spec=JDownloaderResolver)
    jd_resolver.tier_name = "jdownloader"
    jd_resolver.can_resolve.return_value = False

    direct_resolver = AsyncMock(spec=DirectResolver)
    direct_resolver.tier_name = "scraper_direct"
    direct_resolver.can_resolve.return_value = True
    direct_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://github.com/app/app/releases/download/v1.0/app.apk",
        filename="app.apk",
        filesize=15000000,
        hoster="github.com",
        tier="scraper_direct",
        original_link="https://github.com/app/app/releases/download/v1.0/app.apk",
    )

    manager = ResolutionManager(
        rd_resolver=rd_resolver,
        jd_resolver=jd_resolver,
        direct_resolver=direct_resolver,
    )

    links = ["https://github.com/app/app/releases/download/v1.0/app.apk"]
    resolved = await manager.resolve(links)

    assert resolved is not None
    assert resolved.tier == "scraper_direct"
    assert resolved.download_url == "https://github.com/app/app/releases/download/v1.0/app.apk"


@pytest.mark.asyncio
async def test_resolution_manager_multi_mirror_priority_sorting():
    """Test ResolutionManager resolves highest priority mirror link."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    
    def rd_resolve_side_effect(link, **kwargs):
        if "turbobit" in link:
            raise UnsupportedHosterError("turbobit is down")
        return ResolvedDownload(
            download_url="https://download.real-debrid.com/d/rg/app.apk",
            filename="app.apk",
            filesize=10000000,
            hoster="rapidgator.net",
            tier="real_debrid",
            original_link=link,
        )

    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.side_effect = rd_resolve_side_effect

    manager = ResolutionManager(rd_resolver=rd_resolver, jd_resolver=None, direct_resolver=None)

    links = [
        "https://turbobit.net/file/123",
        "https://rapidgator.net/file/456",
    ]
    resolved = await manager.resolve(links)

    assert resolved is not None
    assert resolved.hoster == "rapidgator.net"
    assert resolved.original_link == "https://rapidgator.net/file/456"


@pytest.mark.asyncio
async def test_resolution_manager_preferred_tier_override():
    """Test ResolutionManager respects preferred_tier parameter."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://download.real-debrid.com/d/rd/app.apk",
        filename="app.apk",
        tier="real_debrid",
        original_link="https://rapidgator.net/file/123",
    )

    jd_resolver = AsyncMock(spec=JDownloaderResolver)
    jd_resolver.tier_name = "jdownloader"
    jd_resolver.can_resolve.return_value = True
    jd_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://rapidgator.net/file/123",
        filename="app.apk",
        tier="jdownloader",
        original_link="https://rapidgator.net/file/123",
    )

    manager = ResolutionManager(rd_resolver=rd_resolver, jd_resolver=jd_resolver)

    resolved = await manager.resolve(
        "https://rapidgator.net/file/123",
        preferred_tier="jdownloader",
    )

    assert resolved is not None
    assert resolved.tier == "jdownloader"
    jd_resolver.resolve.assert_awaited_once()
    rd_resolver.resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolution_manager_resolve_all():
    """Test resolve_all attempts resolution for all links in list."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.tier_name = "real_debrid"
    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.side_effect = lambda link, **kw: ResolvedDownload(
        download_url=f"https://rd.com/{link}",
        original_link=link,
        tier="real_debrid",
    )

    manager = ResolutionManager(rd_resolver=rd_resolver)
    results = await manager.resolve_all(["https://rapidgator.net/1", "https://rapidgator.net/2"])

    assert len(results) == 2
    assert results[0].original_link == "https://rapidgator.net/1"
    assert results[1].original_link == "https://rapidgator.net/2"


@pytest.mark.asyncio
async def test_resolution_manager_all_fail_returns_none():
    """Test ResolutionManager returns None when all resolvers fail for all links."""
    rd_resolver = AsyncMock(spec=RealDebridResolver)
    rd_resolver.can_resolve.return_value = True
    rd_resolver.resolve.side_effect = ResolverError("Failure")

    jd_resolver = AsyncMock(spec=JDownloaderResolver)
    jd_resolver.can_resolve.return_value = False

    direct_resolver = AsyncMock(spec=DirectResolver)
    direct_resolver.can_resolve.return_value = False

    manager = ResolutionManager(
        rd_resolver=rd_resolver,
        jd_resolver=jd_resolver,
        direct_resolver=direct_resolver,
    )

    resolved = await manager.resolve(["https://broken-link.com/123"])
    assert resolved is None


# ---------------------------------------------------------------------------
# 6. Additional Edge Case Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_debrid_can_resolve_cached_hosts():
    """Test can_resolve uses cached supported hosts."""
    resolver = RealDebridResolver(api_token="valid_token")
    resolver._cached_hosts = ["customhost.xyz", "mirror.net"]

    assert await resolver.can_resolve("https://customhost.xyz/file/123") is True
    assert await resolver.can_resolve("https://sub.customhost.xyz/file/123") is True
    assert await resolver.can_resolve("https://unsupported.com/file/123") is False


@pytest.mark.asyncio
async def test_real_debrid_get_supported_hosts_unconfigured():
    """Test get_supported_hosts returns empty list when unconfigured."""
    resolver = RealDebridResolver(api_token="")
    assert await resolver.get_supported_hosts() == []


@pytest.mark.asyncio
async def test_real_debrid_get_supported_hosts_default_client():
    """Test get_supported_hosts with default internal client and alternative payload formats."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "host1.com": "up",
        "host2.com": "down",
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch("apkpipe.resolvers.real_debrid.httpx.AsyncClient", return_value=mock_client):
        resolver = RealDebridResolver(api_token="valid_token")
        hosts = await resolver.get_supported_hosts()
        assert "host1.com" in hosts
        assert "host2.com" not in hosts
        mock_client.aclose.assert_awaited_once()

    # List format response
    mock_resp_list = MagicMock(spec=httpx.Response)
    mock_resp_list.status_code = 200
    mock_resp_list.json.return_value = ["hostA.com", "hostB.com"]
    mock_client_list = AsyncMock()
    mock_client_list.get.return_value = mock_resp_list
    with patch("apkpipe.resolvers.real_debrid.httpx.AsyncClient", return_value=mock_client_list):
        resolver = RealDebridResolver(api_token="valid_token")
        hosts = await resolver.get_supported_hosts()
        assert hosts == ["hostA.com", "hostB.com"]


@pytest.mark.asyncio
async def test_real_debrid_get_supported_hosts_errors():
    """Test error handling in get_supported_hosts."""
    mock_resp_auth = MagicMock(spec=httpx.Response)
    mock_resp_auth.status_code = 401
    mock_client_auth = AsyncMock()
    mock_client_auth.get.return_value = mock_resp_auth

    resolver = RealDebridResolver(api_token="bad_token")
    with pytest.raises(AuthenticationError, match="Invalid or expired"):
        await resolver.get_supported_hosts(client=mock_client_auth)

    mock_client_err = AsyncMock()
    mock_client_err.get.side_effect = httpx.ConnectError("Connection failed")
    with pytest.raises(ResolverError, match="Failed to query supported hosts"):
        await resolver.get_supported_hosts(client=mock_client_err)


@pytest.mark.asyncio
async def test_real_debrid_check_link_edge_cases():
    """Test check_link unconfigured, password handling, and error handling."""
    unconf = RealDebridResolver(api_token="")
    with pytest.raises(AuthenticationError, match="not configured"):
        await unconf.check_link("https://rapidgator.net/123")

    mock_resp_auth = MagicMock(spec=httpx.Response)
    mock_resp_auth.status_code = 403
    mock_client_auth = AsyncMock()
    mock_client_auth.post.return_value = mock_resp_auth
    conf = RealDebridResolver(api_token="tok")
    with pytest.raises(AuthenticationError, match="Invalid or expired"):
        await conf.check_link("https://rg.to/123", password="pass", client=mock_client_auth)

    mock_client_err = AsyncMock()
    mock_client_err.post.side_effect = httpx.ConnectError("Failed")
    with pytest.raises(ResolverError, match="Failed to check link"):
        await conf.check_link("https://rg.to/123", client=mock_client_err)

    # Default internal client
    mock_resp_ok = MagicMock(spec=httpx.Response)
    mock_resp_ok.status_code = 200
    mock_resp_ok.json.return_value = {"supported": 1}
    mock_client_ok = AsyncMock()
    mock_client_ok.post.return_value = mock_resp_ok
    with patch("apkpipe.resolvers.real_debrid.httpx.AsyncClient", return_value=mock_client_ok):
        res = await conf.check_link("https://rg.to/123")
        assert res["supported"] == 1
        mock_client_ok.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_debrid_resolve_additional_errors():
    """Test RealDebridResolver response errors: 404, 500, missing download URL, unknown error."""
    resolver = RealDebridResolver(api_token="valid_token")

    # 404 without error payload
    mock_resp_404 = MagicMock(spec=httpx.Response)
    mock_resp_404.status_code = 404
    mock_resp_404.json.side_effect = Exception("Not JSON")
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp_404
    with pytest.raises(LinkDeadError, match="404"):
        await resolver.resolve("https://rg.to/file/dead", client=mock_client)

    # 500 without error payload
    mock_resp_500 = MagicMock(spec=httpx.Response)
    mock_resp_500.status_code = 500
    mock_resp_500.text = "Internal Server Error"
    mock_resp_500.json.side_effect = Exception("Not JSON")
    mock_client.post.return_value = mock_resp_500
    with pytest.raises(ResolverError, match="status 500"):
        await resolver.resolve("https://rg.to/file/err", client=mock_client)

    # Missing download URL in 200 OK
    mock_resp_nodl = MagicMock(spec=httpx.Response)
    mock_resp_nodl.status_code = 200
    mock_resp_nodl.json.return_value = {"id": "123", "filename": "app.apk"}
    mock_client.post.return_value = mock_resp_nodl
    with pytest.raises(ResolverError, match="missing download URL"):
        await resolver.resolve("https://rg.to/file/nodl", client=mock_client)

    # Generic Real-Debrid error payload
    mock_resp_gen = MagicMock(spec=httpx.Response)
    mock_resp_gen.status_code = 400
    mock_resp_gen.json.return_value = {"error": "unknown_issue", "error_code": 99}
    mock_client.post.return_value = mock_resp_gen
    with pytest.raises(ResolverError, match="unknown_issue"):
        await resolver.resolve("https://rg.to/file/gen", client=mock_client)


@pytest.mark.asyncio
async def test_direct_resolver_edge_cases():
    """Test DirectResolver with invalid URLs and resolve failures."""
    resolver = DirectResolver()

    assert await resolver.can_resolve("") is False
    assert await resolver.can_resolve("ftp://example.com/file.apk") is False
    assert await resolver.can_resolve("invalid-url") is False

    # resolve on unresolvable URL
    assert await resolver.resolve("https://example.com/page.html") is None

    # URL without filename
    res = await resolver.resolve("https://example.com/.apk")
    assert res is not None
    assert res.filename == ".apk"


def test_jdownloader_create_crawljob_edge_cases(tmp_path: Path):
    """Test create_crawljob without watch_dir and with extra kwargs."""
    resolver = JDownloaderResolver(watch_dir=None, email="", password="")
    with pytest.raises(ResolverError, match="Watch directory is not configured"):
        resolver.create_crawljob("https://example.com/file.apk")

    resolver_watch = JDownloaderResolver(watch_dir=str(tmp_path))
    job_file = resolver_watch.create_crawljob(
        link="https://example.com/file.apk",
        package_name="App",
        download_dir="/downloads",
        filename="app.apk",
        customComment="AutoDownloaded",
        extraTag=123,
    )
    content = job_file.read_text()
    assert "customComment=AutoDownloaded" in content
    assert "extraTag=123" in content


@pytest.mark.asyncio
async def test_jdownloader_api_client_edge_cases():
    """Test MyJDownloader API client defaults and HTTP errors."""
    mock_resp_conn = MagicMock(spec=httpx.Response)
    mock_resp_conn.status_code = 200
    mock_resp_conn.json.return_value = {"data": {"sessiontoken": "tok123"}}

    mock_resp_dev = MagicMock(spec=httpx.Response)
    mock_resp_dev.status_code = 200
    mock_resp_dev.json.return_value = {"data": {"list": [{"name": "DefaultNAS", "id": "dev_default"}]}}

    mock_resp_add = MagicMock(spec=httpx.Response)
    mock_resp_add.status_code = 200
    mock_resp_add.json.return_value = {"data": {"packageId": "p1"}}

    mock_client = AsyncMock()
    mock_client.post.side_effect = [mock_resp_conn, mock_resp_dev, mock_resp_add]

    with patch("apkpipe.resolvers.jdownloader.httpx.AsyncClient", return_value=mock_client):
        resolver = JDownloaderResolver(
            watch_dir=None,
            email="u@example.com",
            password="p",
            device_name=None,
        )
        resolved = await resolver.resolve("https://example.com/app.apk")
        assert resolved is not None
        assert resolved.metadata["device_id"] == "dev_default"
        mock_client.aclose.assert_awaited_once()

    # Network HTTPError
    mock_client_err = AsyncMock()
    mock_client_err.post.side_effect = httpx.ConnectError("JD API unreachable")
    resolver_err = JDownloaderResolver(
        watch_dir=None,
        email="u@example.com",
        password="p",
    )
    with pytest.raises(ResolverError, match="JD API unreachable"):
        await resolver_err.resolve("https://example.com/app.apk", client=mock_client_err)


@pytest.mark.asyncio
async def test_resolution_manager_edge_cases():
    """Test ResolutionManager handling empty links, exceptions in resolvers, and defaults."""
    manager = ResolutionManager()

    # Empty inputs
    assert await manager.resolve([]) is None
    assert await manager.resolve("") is None

    # Single string link
    res = await manager.resolve("https://example.com/app.apk")
    assert res is not None
    assert res.tier == "scraper_direct"

    # Resolver throwing unhandled exception is caught and skipped
    faulty_resolver = AsyncMock(spec=RealDebridResolver)
    faulty_resolver.tier_name = "real_debrid"
    faulty_resolver.can_resolve.return_value = True
    faulty_resolver.resolve.side_effect = RuntimeError("Fatal crash")

    direct_resolver = AsyncMock(spec=DirectResolver)
    direct_resolver.tier_name = "scraper_direct"
    direct_resolver.can_resolve.return_value = True
    direct_resolver.resolve.return_value = ResolvedDownload(
        download_url="https://example.com/app.apk",
        original_link="https://example.com/app.apk",
    )

    manager_faulty = ResolutionManager(
        rd_resolver=faulty_resolver,
        jd_resolver=None,
        direct_resolver=direct_resolver,
    )
    resolved = await manager_faulty.resolve(["https://example.com/app.apk"])
    assert resolved is not None
    assert resolved.download_url == "https://example.com/app.apk"

