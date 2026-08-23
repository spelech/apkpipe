"""Unit tests for AllDebrid link resolver."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from apkpipe.resolvers.all_debrid import AllDebridResolver, KNOWN_AD_HOSTERS
from apkpipe.resolvers.base import (
    AuthenticationError,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    ResolverError,
    UnsupportedHosterError,
)


@pytest.mark.asyncio
async def test_alldebrid_unconfigured():
    """Test unconfigured resolver returns False for can_resolve and None for resolve."""
    resolver = AllDebridResolver(api_key=None)
    assert not resolver.is_configured
    assert not await resolver.can_resolve("https://rapidgator.net/file/123/sample.rar")
    result = await resolver.resolve("https://rapidgator.net/file/123/sample.rar")
    assert result is None
    assert await resolver.get_supported_hosts() == []


@pytest.mark.asyncio
async def test_alldebrid_can_resolve_configured():
    """Test domain checking for configured AllDebrid resolver."""
    resolver = AllDebridResolver(api_key="valid_test_key")
    assert resolver.is_configured
    assert await resolver.can_resolve("https://rapidgator.net/file/123/sample.rar")
    assert await resolver.can_resolve("https://1fichier.com/?abcdef")
    assert await resolver.can_resolve("https://mega.nz/file/xyz123")
    assert await resolver.can_resolve("https://sub.rapidgator.net/file/123")
    assert not await resolver.can_resolve("https://unknownhost12345.com/file")
    assert not await resolver.can_resolve("not_a_url")
    assert not await resolver.can_resolve("ftp://random.com/file")
    assert not await resolver.can_resolve("")
    assert not await resolver.can_resolve("http://")


def test_alldebrid_init_fallback():
    """Test AllDebridResolver initialization fallback to settings."""
    resolver = AllDebridResolver(api_key="explicit_key", agent="custom_app")
    assert resolver.api_key == "explicit_key"
    assert resolver.agent == "custom_app"
    assert resolver.is_configured is True

    with patch("apkpipe.resolvers.all_debrid.get_settings") as mock_settings:
        mock_settings.return_value.alldebrid_api_key = "settings_key"
        mock_settings.return_value.alldebrid_agent = "settings_agent"
        res = AllDebridResolver()
        assert res.api_key == "settings_key"
        assert res.agent == "settings_agent"
        assert res.is_configured is True

    with patch("apkpipe.resolvers.all_debrid.get_settings") as mock_settings:
        mock_settings.return_value = object()
        res_empty = AllDebridResolver(agent="apkpipe")
        assert res_empty.api_key == ""
        assert res_empty.agent == "apkpipe"
        assert res_empty.is_configured is False


@pytest.mark.asyncio
async def test_alldebrid_successful_resolve():
    """Test successful link resolution returning ResolvedDownload."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "link": "https://debrid.alldebrid.com/dl/sample.rar",
            "filename": "sample.apk",
            "filesize": 52428800,
            "host": "rapidgator",
        },
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_test_key", agent="testagent")
    link = "https://rapidgator.net/file/123/sample.rar"
    result = await resolver.resolve(link, password="test_password", client=mock_client)

    assert isinstance(result, ResolvedDownload)
    assert result.download_url == "https://debrid.alldebrid.com/dl/sample.rar"
    assert result.filename == "sample.apk"
    assert result.filesize == 52428800
    assert result.hoster == "rapidgator"
    assert result.tier == "alldebrid"
    assert result.original_link == link
    assert result.metadata["filename"] == "sample.apk"

    mock_client.get.assert_awaited_once()
    call_args, call_kwargs = mock_client.get.call_args
    assert "https://api.alldebrid.com/v4/link/unlock" in call_args[0]
    assert call_kwargs["params"]["link"] == link
    assert call_kwargs["params"]["apikey"] == "valid_test_key"
    assert call_kwargs["params"]["agent"] == "testagent"
    assert call_kwargs["params"]["password"] == "test_password"


@pytest.mark.asyncio
async def test_alldebrid_auth_error():
    """Test AUTH_BAD_APIKEY raises AuthenticationError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "AUTH_BAD_APIKEY", "message": "Invalid API key"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="invalid_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    with pytest.raises(AuthenticationError, match="AUTH_BAD_APIKEY"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_auth_blocked():
    """Test AUTH_BLOCKED raises AuthenticationError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "AUTH_BLOCKED", "message": "Account blocked"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="blocked_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    with pytest.raises(AuthenticationError, match="AUTH_BLOCKED"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_auth_must_be_premium():
    """Test MUST_BE_PREMIUM raises AuthenticationError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "MUST_BE_PREMIUM", "message": "Premium expired"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="expired_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(AuthenticationError, match="MUST_BE_PREMIUM"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_link_dead():
    """Test LINK_DEAD raises LinkDeadError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "LINK_DEAD", "message": "File not found"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    with pytest.raises(LinkDeadError, match="LINK_DEAD"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_link_down():
    """Test LINK_DOWN raises LinkDeadError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "LINK_DOWN", "message": "Link is down"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123/sample.rar"
    with pytest.raises(LinkDeadError, match="LINK_DOWN"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_host_not_supported():
    """Test LINK_HOST_NOT_SUPPORTED raises UnsupportedHosterError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "LINK_HOST_NOT_SUPPORTED", "message": "Host not supported"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://unknownhost.com/file/123"
    with pytest.raises(UnsupportedHosterError, match="LINK_HOST_NOT_SUPPORTED"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_host_not_available():
    """Test HOST_NOT_AVAILABLE raises UnsupportedHosterError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "HOST_NOT_AVAILABLE", "message": "Hoster temp unavailable"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(UnsupportedHosterError, match="HOST_NOT_AVAILABLE"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_rate_limited():
    """Test RATE_LIMITED error code raises RateLimitError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "RATE_LIMITED", "message": "Too many requests"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(RateLimitError, match="RATE_LIMITED"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_http_401():
    """Test HTTP 401 status raises AuthenticationError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="bad_token")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(AuthenticationError, match="401"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_http_403():
    """Test HTTP 403 status raises AuthenticationError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="forbidden_token")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(AuthenticationError, match="403"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_http_429():
    """Test HTTP 429 status raises RateLimitError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.text = "Too Many Requests"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(RateLimitError, match="429"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_http_404():
    """Test HTTP 404 status raises LinkDeadError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(LinkDeadError, match="404"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_http_500():
    """Test HTTP 500 status raises ResolverError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.json.side_effect = Exception("Not JSON")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(ResolverError, match="status 500"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_generic_error():
    """Test generic unknown error raises ResolverError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": {"code": "UNKNOWN_ERROR", "message": "Something went wrong"},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(ResolverError, match="UNKNOWN_ERROR"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_error_as_string():
    """Test error returned as a string in payload."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "error",
        "error": "AUTH_BAD_APIKEY",
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(AuthenticationError, match="AUTH_BAD_APIKEY"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_missing_payload_data():
    """Test response with missing data dict raises ResolverError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "success", "data": None}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(ResolverError, match="missing data payload"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_missing_download_link():
    """Test response with missing download link raises ResolverError."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "success", "data": {"filename": "app.apk"}}
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(ResolverError, match="missing download link"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_network_error():
    """Test network error during resolve raises ResolverError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.ConnectError("Connection refused")

    resolver = AllDebridResolver(api_key="valid_key")
    link = "https://rapidgator.net/file/123"
    with pytest.raises(ResolverError, match="network error"):
        await resolver.resolve(link, client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_get_supported_hosts():
    """Test fetching remote supported hosts list."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "hosts": {
                "rapidgator": {"status": True, "domains": ["rapidgator.net", "rg.to"]},
                "nitroflare": {"status": False, "domains": ["nitroflare.com"]},
                "1fichier": {"status": True, "domain": "1fichier.com"},
                "customhost.com": True,
            }
        },
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    hosts = await resolver.get_supported_hosts(client=mock_client)
    assert "rapidgator.net" in hosts
    assert "rg.to" in hosts
    assert "1fichier.com" in hosts
    assert "customhost.com" in hosts
    assert "nitroflare.com" not in hosts
    assert await resolver.can_resolve("https://rapidgator.net/file/123")
    assert await resolver.can_resolve("https://customhost.com/file/123")


@pytest.mark.asyncio
async def test_alldebrid_get_supported_hosts_list_format():
    """Test fetching remote supported hosts list when data is a list."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "hosts": ["rapidgator.net", {"domain": "mega.nz"}]
        },
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="valid_key")
    hosts = await resolver.get_supported_hosts(client=mock_client)
    assert "rapidgator.net" in hosts
    assert "mega.nz" in hosts


@pytest.mark.asyncio
async def test_alldebrid_get_supported_hosts_auth_error():
    """Test get_supported_hosts handles 401 auth error."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    resolver = AllDebridResolver(api_key="bad_key")
    with pytest.raises(AuthenticationError, match="expired AllDebrid API key"):
        await resolver.get_supported_hosts(client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_get_supported_hosts_http_error():
    """Test get_supported_hosts handles connection errors."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.ConnectError("Network down")

    resolver = AllDebridResolver(api_key="valid_key")
    with pytest.raises(ResolverError, match="Failed to query supported hosts"):
        await resolver.get_supported_hosts(client=mock_client)


@pytest.mark.asyncio
async def test_alldebrid_resolve_internal_client():
    """Test resolve with default internal client."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "link": "https://debrid.alldebrid.com/dl/sample.rar",
            "filename": "sample.apk",
            "filesize": 1000,
            "host": "rapidgator",
        },
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    with patch("httpx.AsyncClient", return_value=mock_client):
        resolver = AllDebridResolver(api_key="valid_test_key")
        result = await resolver.resolve("https://rapidgator.net/file/123")
        assert result is not None
        assert result.download_url == "https://debrid.alldebrid.com/dl/sample.rar"
        mock_client.aclose.assert_awaited_once()
