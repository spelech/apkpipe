"""Unit tests for notification dispatch service (Apprise and Ntfy)."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from apkpipe.notifications.apprise import (
    NotificationEvent,
    NotificationService,
    NotificationSeverity,
    format_bytes,
    send_notification,
)


@pytest.fixture
def mock_httpx_client():
    """Create a mock AsyncClient for httpx."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


# --- Byte Formatting Tests ---

def test_format_bytes():
    """Verify human-readable byte formatting."""
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1048576) == "1.00 MB"
    assert format_bytes(52428800) == "50.00 MB"
    assert format_bytes(1073741824) == "1.00 GB"
    assert format_bytes(None) == "Unknown size"


# --- Initialization Tests ---

def test_notification_service_init_defaults():
    """Verify NotificationService initializes with default settings."""
    service = NotificationService()
    assert service.apprise_url == ""
    assert service.ntfy_topic == ""
    assert service.ntfy_url == "https://ntfy.sh"
    assert service.timeout == 10.0


def test_notification_service_init_custom():
    """Verify NotificationService initializes with explicit parameters."""
    service = NotificationService(
        apprise_url="http://apprise.local:8000/notify",
        ntfy_url="https://custom-ntfy.homelab",
        ntfy_topic="my-apk-topic",
        timeout=5.0,
    )
    assert service.apprise_url == "http://apprise.local:8000/notify"
    assert service.ntfy_url == "https://custom-ntfy.homelab"
    assert service.ntfy_topic == "my-apk-topic"
    assert service.timeout == 5.0


def test_notification_service_configured_property():
    """Verify is_configured property reflects whether any endpoint is set."""
    empty = NotificationService(apprise_url="", ntfy_topic="")
    assert empty.is_configured is False

    with_apprise = NotificationService(apprise_url="http://apprise:8000/notify", ntfy_topic="")
    assert with_apprise.is_configured is True

    with_ntfy = NotificationService(apprise_url="", ntfy_topic="alerts")
    assert with_ntfy.is_configured is True


# --- Apprise Dispatch Tests ---

@pytest.mark.asyncio
async def test_send_apprise_success(mock_httpx_client):
    """Verify successful dispatch to Apprise HTTP server."""
    mock_response = httpx.Response(status_code=200, json={"status": "ok"})
    mock_httpx_client.post.return_value = mock_response

    service = NotificationService(
        apprise_url="http://apprise:8000/notify",
        http_client=mock_httpx_client,
    )

    success = await service.send_apprise(
        title="APKPipe Download Complete",
        body="Successfully downloaded Spotify v8.9.0",
        tags=["apkpipe", "success"],
        severity=NotificationSeverity.SUCCESS,
    )

    assert success is True
    mock_httpx_client.post.assert_awaited_once()
    call_args = mock_httpx_client.post.await_args
    assert call_args[0][0] == "http://apprise:8000/notify"
    json_data = call_args[1]["json"]
    assert json_data["title"] == "APKPipe Download Complete"
    assert json_data["body"] == "Successfully downloaded Spotify v8.9.0"
    assert json_data["type"] == "success"
    assert "apkpipe" in json_data["tag"]


@pytest.mark.asyncio
async def test_send_apprise_with_internal_client():
    """Verify send_apprise creates and closes internal httpx client when not provided."""
    service = NotificationService(apprise_url="http://apprise:8000/notify")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.aclose", new_callable=AsyncMock) as mock_close:
        mock_post.return_value = httpx.Response(status_code=200, json={"status": "ok"})

        success = await service.send_apprise(title="Internal Client Test", body="Body")
        assert success is True
        mock_post.assert_awaited_once()
        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_apprise_http_error(mock_httpx_client):
    """Verify send_apprise handles HTTP 500 error gracefully without raising."""
    mock_response = httpx.Response(status_code=500, text="Internal Server Error")
    mock_httpx_client.post.return_value = mock_response

    service = NotificationService(
        apprise_url="http://apprise:8000/notify",
        http_client=mock_httpx_client,
    )

    success = await service.send_apprise(
        title="Test Title",
        body="Test Body",
    )
    assert success is False


@pytest.mark.asyncio
async def test_send_apprise_network_exception(mock_httpx_client):
    """Verify send_apprise handles network exceptions gracefully."""
    mock_httpx_client.post.side_effect = httpx.ConnectError("Connection refused")

    service = NotificationService(
        apprise_url="http://apprise:8000/notify",
        http_client=mock_httpx_client,
    )

    success = await service.send_apprise(
        title="Test Title",
        body="Test Body",
    )
    assert success is False


@pytest.mark.asyncio
async def test_send_apprise_no_url():
    """Verify send_apprise returns False if no apprise_url is configured."""
    service = NotificationService(apprise_url="")
    success = await service.send_apprise(title="Test", body="Body")
    assert success is False


# --- Ntfy Dispatch Tests ---

@pytest.mark.asyncio
async def test_send_ntfy_success(mock_httpx_client):
    """Verify successful dispatch to Ntfy endpoint."""
    mock_response = httpx.Response(status_code=200, text="OK")
    mock_httpx_client.post.return_value = mock_response

    service = NotificationService(
        ntfy_url="https://ntfy.sh",
        ntfy_topic="my-apk-topic",
        http_client=mock_httpx_client,
    )

    success = await service.send_ntfy(
        title="APKPipe Download Complete",
        body="Downloaded Spotify v8.9.0",
        tags=["package", "white_check_mark"],
        priority="high",
        click="https://nextcloud.local/apps/files",
    )

    assert success is True
    mock_httpx_client.post.assert_awaited_once()
    call_args = mock_httpx_client.post.await_args
    assert call_args[0][0] == "https://ntfy.sh/my-apk-topic"
    headers = call_args[1]["headers"]
    assert headers["Title"] == "APKPipe Download Complete"
    assert headers["Priority"] == "high"
    assert headers["Click"] == "https://nextcloud.local/apps/files"
    assert "package" in headers["Tags"]
    assert headers["Markdown"] == "yes"
    assert call_args[1]["content"] == "Downloaded Spotify v8.9.0".encode("utf-8")


@pytest.mark.asyncio
async def test_send_ntfy_with_internal_client():
    """Verify send_ntfy creates and closes internal httpx client when not provided."""
    service = NotificationService(ntfy_topic="my-topic")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.aclose", new_callable=AsyncMock) as mock_close:
        mock_post.return_value = httpx.Response(status_code=200, text="OK")

        success = await service.send_ntfy(title="Internal Client Test", body="Body")
        assert success is True
        mock_post.assert_awaited_once()
        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_ntfy_http_error(mock_httpx_client):
    """Verify send_ntfy handles HTTP 404/500 errors gracefully."""
    mock_response = httpx.Response(status_code=404, text="Topic Not Found")
    mock_httpx_client.post.return_value = mock_response

    service = NotificationService(
        ntfy_topic="nonexistent",
        http_client=mock_httpx_client,
    )

    success = await service.send_ntfy(title="Test", body="Body")
    assert success is False


@pytest.mark.asyncio
async def test_send_ntfy_network_timeout(mock_httpx_client):
    """Verify send_ntfy handles timeout exceptions gracefully."""
    mock_httpx_client.post.side_effect = httpx.TimeoutException("Request timed out")

    service = NotificationService(
        ntfy_topic="my-topic",
        http_client=mock_httpx_client,
    )

    success = await service.send_ntfy(title="Test", body="Body")
    assert success is False


@pytest.mark.asyncio
async def test_send_ntfy_no_topic():
    """Verify send_ntfy returns False when ntfy_topic is empty."""
    service = NotificationService(ntfy_topic="")
    success = await service.send_ntfy(title="Test", body="Body")
    assert success is False


# --- Multi-Target send_notification Tests ---

@pytest.mark.asyncio
async def test_send_notification_both_targets(mock_httpx_client):
    """Verify send_notification dispatches to both Apprise and Ntfy when configured."""
    mock_httpx_client.post.return_value = httpx.Response(status_code=200, text="OK")

    service = NotificationService(
        apprise_url="http://apprise:8000/notify",
        ntfy_topic="my-topic",
        http_client=mock_httpx_client,
    )

    result = await service.send_notification(
        title="Test Release",
        body="Release body content",
        event_type=NotificationEvent.DOWNLOAD_COMPLETED,
        tags=["test"],
        severity=NotificationSeverity.SUCCESS,
    )

    assert result is True
    assert mock_httpx_client.post.await_count == 2


@pytest.mark.asyncio
async def test_send_notification_ntfy_default_priority(mock_httpx_client):
    """Verify severity=FAILURE maps to high priority when priority is not specified."""
    mock_httpx_client.post.return_value = httpx.Response(status_code=200, text="OK")

    service = NotificationService(
        ntfy_topic="my-topic",
        http_client=mock_httpx_client,
    )

    result = await service.send_notification(
        title="Failed Alert",
        body="Something failed",
        severity=NotificationSeverity.FAILURE,
    )

    assert result is True
    call_args = mock_httpx_client.post.await_args
    assert call_args[1]["headers"]["Priority"] == "high"


@pytest.mark.asyncio
async def test_send_notification_partial_success(mock_httpx_client):
    """Verify send_notification returns True if at least one endpoint succeeds."""
    # Apprise fails, Ntfy succeeds
    mock_httpx_client.post.side_effect = [
        httpx.Response(status_code=500, text="Apprise down"),
        httpx.Response(status_code=200, text="Ntfy ok"),
    ]

    service = NotificationService(
        apprise_url="http://apprise:8000/notify",
        ntfy_topic="my-topic",
        http_client=mock_httpx_client,
    )

    result = await service.send_notification(
        title="Test Partial",
        body="Testing partial dispatch",
    )

    assert result is True


@pytest.mark.asyncio
async def test_send_notification_none_configured():
    """Verify send_notification returns False if neither endpoint is configured."""
    service = NotificationService(apprise_url="", ntfy_topic="")
    result = await service.send_notification(title="Test", body="Body")
    assert result is False


# --- Event-Specific Helper Method Tests ---

@pytest.mark.asyncio
async def test_notify_download_started():
    """Verify notify_download_started formats title, body, and tags properly."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_started(
            app_name="Spotify",
            version="8.9.0",
            releaser="Balatan",
            feed_title="Spotify Music v8.9.0 [Mod]",
        )

        assert result is True
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.await_args[1]
        assert "Spotify" in call_kwargs["title"]
        assert "8.9.0" in call_kwargs["title"]
        assert "Balatan" in call_kwargs["body"]
        assert call_kwargs["event_type"] == NotificationEvent.DOWNLOAD_STARTED
        assert call_kwargs["severity"] == NotificationSeverity.INFO


@pytest.mark.asyncio
async def test_notify_download_started_minimal():
    """Verify notify_download_started without optional version/releaser/feed_title."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_started(app_name="MinimalApp")
        assert result is True
        call_kwargs = mock_send.await_args[1]
        assert call_kwargs["title"] == "[APKPipe] Download Started: MinimalApp"


@pytest.mark.asyncio
async def test_notify_download_completed():
    """Verify notify_download_completed formats target path, file size, and tier."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_completed(
            app_name="Nova Launcher",
            version="8.0.14",
            releaser="Prime",
            target_path="/data/downloads/Nova Launcher/Nova Launcher v8.0.14.apk",
            file_size=25165824,
            download_tier="real_debrid",
        )

        assert result is True
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.await_args[1]
        assert "Nova Launcher" in call_kwargs["title"]
        assert "8.0.14" in call_kwargs["title"]
        assert "24.00 MB" in call_kwargs["body"]
        assert "real_debrid" in call_kwargs["body"]
        assert "/data/downloads/Nova Launcher/Nova Launcher v8.0.14.apk" in call_kwargs["body"]
        assert call_kwargs["event_type"] == NotificationEvent.DOWNLOAD_COMPLETED
        assert call_kwargs["severity"] == NotificationSeverity.SUCCESS


@pytest.mark.asyncio
async def test_notify_download_completed_minimal():
    """Verify notify_download_completed with minimal args."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_completed(app_name="MinimalApp")
        assert result is True
        call_kwargs = mock_send.await_args[1]
        assert call_kwargs["title"] == "[APKPipe] Download Complete: MinimalApp"


@pytest.mark.asyncio
async def test_notify_download_failed():
    """Verify notify_download_failed includes error message and failure severity."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_failed(
            app_name="InShot Pro",
            version="2.0",
            releaser="derrin",
            error="All mirror resolvers exhausted: Rapidgator hoster unavailable",
        )

        assert result is True
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.await_args[1]
        assert "Failed" in call_kwargs["title"]
        assert "InShot Pro" in call_kwargs["title"]
        assert "Rapidgator" in call_kwargs["body"]
        assert call_kwargs["event_type"] == NotificationEvent.DOWNLOAD_FAILED
        assert call_kwargs["severity"] == NotificationSeverity.FAILURE


@pytest.mark.asyncio
async def test_notify_download_failed_minimal():
    """Verify notify_download_failed with minimal args."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_download_failed(app_name="MinimalApp")
        assert result is True
        call_kwargs = mock_send.await_args[1]
        assert call_kwargs["title"] == "[APKPipe] Download Failed: MinimalApp"


@pytest.mark.asyncio
async def test_notify_feed_matched():
    """Verify notify_feed_matched notifies on watchlist filter match."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_feed_matched(
            app_name="TiviMate IPTV Player",
            version="4.7.0",
            releaser="RockMODS",
            feed_title="TiviMate IPTV Player Premium v4.7.0 [RockMODS]",
        )

        assert result is True
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.await_args[1]
        assert "TiviMate" in call_kwargs["title"]
        assert "4.7.0" in call_kwargs["title"]
        assert "RockMODS" in call_kwargs["body"]
        assert call_kwargs["event_type"] == NotificationEvent.FEED_MATCHED
        assert call_kwargs["severity"] == NotificationSeverity.INFO


@pytest.mark.asyncio
async def test_notify_feed_matched_minimal():
    """Verify notify_feed_matched with minimal args."""
    service = NotificationService()
    with patch.object(service, "send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        result = await service.notify_feed_matched(app_name="MinimalApp")
        assert result is True
        call_kwargs = mock_send.await_args[1]
        assert call_kwargs["title"] == "[APKPipe] New Release Matched: MinimalApp"


# --- Standalone Module Function Test ---

@pytest.mark.asyncio
async def test_module_send_notification():
    """Verify standalone send_notification function works."""
    with patch("apkpipe.notifications.apprise.NotificationService.send_notification", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res = await send_notification("Global Alert", "Global body")
        assert res is True
        mock_send.assert_awaited_once_with(
            title="Global Alert",
            body="Global body",
            event_type=NotificationEvent.DOWNLOAD_COMPLETED,
            tags=None,
            severity=NotificationSeverity.INFO,
        )
