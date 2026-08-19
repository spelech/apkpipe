"""Unit tests for Nextcloud OCC integration and files:scan execution."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from apkpipe.integrations.nextcloud import (
    NextcloudClient,
    NextcloudStrategy,
    OccScanResult,
    format_scan_path,
    parse_occ_output,
    trigger_occ_scan,
)


@pytest.fixture
def mock_httpx_client():
    """Create a mock AsyncClient for httpx."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


# --- Output Parsing & Path Formatting Tests ---

def test_format_scan_path():
    """Verify scan path formatting for relative and absolute paths with user prefix."""
    # Simple path
    assert format_scan_path("/data/downloads/Spotify/Spotify v8.9.0.apk") == "/Spotify/Spotify v8.9.0.apk"
    
    # With base_download_dir specified
    assert format_scan_path(
        "/data/downloads/Spotify/Spotify.apk",
        base_dir="/data/downloads",
    ) == "/Spotify/Spotify.apk"

    # With user specified
    assert format_scan_path(
        "/data/downloads/Spotify/Spotify.apk",
        base_dir="/data/downloads",
        user="admin",
    ) == "/admin/files/Spotify/Spotify.apk"

    # With path already formatted for user
    assert format_scan_path("/admin/files/Spotify/Spotify.apk", user="admin") == "/admin/files/Spotify/Spotify.apk"

    # Path object input
    assert format_scan_path(Path("/data/downloads/Apps/App.apk"), base_dir="/data/downloads") == "/Apps/App.apk"


def test_parse_occ_output():
    """Verify parsing summary counts from standard Nextcloud occ files:scan output."""
    sample_output = """
Starting scan for user 1 out of 1 (admin)
Folder /admin/files/APKs
File /admin/files/APKs/Spotify/Spotify v8.9.0.apk
+---------+-------+--------------+
| Folders | Files | Elapsed time |
+---------+-------+--------------+
| 4       | 18    | 00:00:03     |
+---------+-------+--------------+
"""
    folders, files = parse_occ_output(sample_output)
    assert folders == 4
    assert files == 18

    # Empty or unparseable output
    f_none, fl_none = parse_occ_output("Some unknown output text")
    assert f_none is None
    assert fl_none is None

    # Empty string
    assert parse_occ_output("") == (None, None)


# --- Initialization Tests ---

def test_nextcloud_client_init_defaults():
    """Verify NextcloudClient initializes with default settings."""
    client = NextcloudClient()
    assert client.nextcloud_url == ""
    assert client.nextcloud_token == ""
    assert client.nextcloud_occ_command == ""
    assert client.docker_container_name == "nextcloud"
    assert client.docker_user == "33"
    assert client.timeout == 60.0


def test_nextcloud_client_init_custom():
    """Verify NextcloudClient initializes with custom parameters."""
    client = NextcloudClient(
        nextcloud_url="https://cloud.homelab.local",
        nextcloud_token="secret_token_123",
        nextcloud_occ_command="docker exec -u 33 my_nc php occ files:scan",
        docker_container_name="my_nc",
        docker_user="www-data",
        timeout=30.0,
    )
    assert client.nextcloud_url == "https://cloud.homelab.local"
    assert client.nextcloud_token == "secret_token_123"
    assert client.nextcloud_occ_command == "docker exec -u 33 my_nc php occ files:scan"
    assert client.docker_container_name == "my_nc"
    assert client.docker_user == "www-data"
    assert client.timeout == 30.0


# --- Strategy 1: CUSTOM_COMMAND Tests ---

@pytest.mark.asyncio
async def test_trigger_occ_custom_command_success():
    """Verify custom command execution executes configured command and parses output."""
    client = NextcloudClient(
        nextcloud_occ_command="docker exec -u 33 nextcloud php occ files:scan",
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (
        b"+---------+-------+--------------+\n| Folders | Files | Elapsed time |\n+---------+-------+--------------+\n| 1       | 2     | 00:00:01     |\n+---------+-------+--------------+\n",
        b"",
    )
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_shell:
        result = await client.trigger_occ_scan(
            path="/data/downloads/Spotify/Spotify v8.9.0.apk",
            user="admin",
        )

        assert result.success is True
        assert result.strategy_used == NextcloudStrategy.CUSTOM_COMMAND
        assert result.scanned_folders_count == 1
        assert result.scanned_files_count == 2
        assert result.error is None
        mock_shell.assert_awaited_once()
        cmd_executed = " ".join(mock_shell.await_args[0])
        assert "docker exec -u 33 nextcloud php occ files:scan" in cmd_executed
        assert "--path=" in cmd_executed


@pytest.mark.asyncio
async def test_trigger_occ_custom_command_user_only():
    """Verify custom command with user and no path appends user name."""
    client = NextcloudClient(nextcloud_occ_command="php occ files:scan")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Scanned user", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_shell:
        result = await client.trigger_occ_scan(user="admin")
        assert result.success is True
        cmd_executed = " ".join(mock_shell.await_args[0])
        assert "admin" in cmd_executed


@pytest.mark.asyncio
async def test_trigger_occ_custom_command_explicit_override():
    """Verify explicit CUSTOM_COMMAND strategy override works."""
    client = NextcloudClient(
        nextcloud_occ_command="php occ files:scan",
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Scanned", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await client.trigger_occ_scan(
            path="/path/to/scan",
            strategy=NextcloudStrategy.CUSTOM_COMMAND,
        )
        assert result.success is True
        assert result.strategy_used == NextcloudStrategy.CUSTOM_COMMAND


@pytest.mark.asyncio
async def test_trigger_occ_custom_command_rescan_all():
    """Verify custom command execution with rescan_all=True passes --all flag."""
    client = NextcloudClient(
        nextcloud_occ_command="php /var/www/nextcloud/occ files:scan",
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Scan completed", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_shell:
        result = await client.trigger_occ_scan(rescan_all=True)

        assert result.success is True
        cmd_executed = " ".join(mock_shell.await_args[0])
        assert "--all" in cmd_executed


@pytest.mark.asyncio
async def test_trigger_occ_custom_command_failure():
    """Verify custom command handles non-zero exit code gracefully without raising."""
    client = NextcloudClient(
        nextcloud_occ_command="php occ files:scan",
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"Error: path does not exist")
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await client.trigger_occ_scan(path="/nonexistent")

        assert result.success is False
        assert result.strategy_used == NextcloudStrategy.CUSTOM_COMMAND
        assert "Error: path does not exist" in result.error


@pytest.mark.asyncio
async def test_trigger_occ_custom_command_generic_exception():
    """Verify custom command handles unexpected OS error gracefully."""
    client = NextcloudClient(nextcloud_occ_command="php occ files:scan")

    with patch("asyncio.create_subprocess_exec", side_effect=OSError("OS fork failed")):
        result = await client.trigger_occ_scan(path="/test")
        assert result.success is False
        assert "OS fork failed" in result.error


# --- Strategy 2: DOCKER_EXEC Tests ---

@pytest.mark.asyncio
async def test_trigger_occ_docker_exec_success():
    """Verify docker exec strategy builds appropriate docker CLI arguments."""
    client = NextcloudClient(
        docker_container_name="homelab_nextcloud_1",
        docker_user="33",
    )

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (
        b"+---------+-------+--------------+\n| Folders | Files | Elapsed time |\n+---------+-------+--------------+\n| 3       | 5     | 00:00:01     |\n+---------+-------+--------------+\n",
        b"",
    )
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await client.trigger_occ_scan(
            path="/data/downloads/TiviMate/TiviMate.apk",
            user="admin",
            strategy=NextcloudStrategy.DOCKER_EXEC,
        )

        assert result.success is True
        assert result.strategy_used == NextcloudStrategy.DOCKER_EXEC
        assert result.scanned_folders_count == 3
        assert result.scanned_files_count == 5
        mock_exec.assert_awaited_once()
        args = mock_exec.await_args[0]
        assert args[0] == "docker"
        assert args[1] == "exec"
        assert "-u" in args
        assert "33" in args
        assert "homelab_nextcloud_1" in args
        assert "occ" in args
        assert "files:scan" in args


@pytest.mark.asyncio
async def test_trigger_occ_docker_exec_rescan_all():
    """Verify docker exec strategy handles rescan_all."""
    client = NextcloudClient(docker_container_name="nc")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Scanned all", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await client.trigger_occ_scan(rescan_all=True, strategy=NextcloudStrategy.DOCKER_EXEC)
        assert result.success is True
        args = mock_exec.await_args[0]
        assert "--all" in args


@pytest.mark.asyncio
async def test_trigger_occ_docker_exec_user_only():
    """Verify docker exec strategy handles user without path."""
    client = NextcloudClient(docker_container_name="nc")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Scanned user admin", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await client.trigger_occ_scan(user="admin", strategy=NextcloudStrategy.DOCKER_EXEC)
        assert result.success is True
        args = mock_exec.await_args[0]
        assert "admin" in args


@pytest.mark.asyncio
async def test_trigger_occ_docker_exec_failure():
    """Verify docker exec handles non-zero exit code gracefully."""
    client = NextcloudClient(docker_container_name="nc")

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"Container nc is not running")
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await client.trigger_occ_scan(strategy=NextcloudStrategy.DOCKER_EXEC)
        assert result.success is False
        assert "Container nc is not running" in result.error


@pytest.mark.asyncio
async def test_trigger_occ_docker_exec_timeout():
    """Verify docker exec timeout is handled gracefully."""
    client = NextcloudClient(docker_container_name="nc", timeout=0.01)

    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await client.trigger_occ_scan(strategy=NextcloudStrategy.DOCKER_EXEC)
        assert result.success is False
        assert "timed out" in result.error.lower()


# --- Strategy 3: API Tests ---

@pytest.mark.asyncio
async def test_trigger_occ_api_success(mock_httpx_client):
    """Verify API strategy sends scan request to Nextcloud endpoint."""
    mock_response = httpx.Response(
        status_code=200,
        json={"status": "success", "message": "Scan triggered"},
    )
    mock_httpx_client.post.return_value = mock_response

    client = NextcloudClient(
        nextcloud_url="https://cloud.example.com",
        nextcloud_token="test_token_abc",
        http_client=mock_httpx_client,
    )

    result = await client.trigger_occ_scan(
        path="/data/downloads/Spotify/Spotify.apk",
        user="admin",
        strategy=NextcloudStrategy.API,
    )

    assert result.success is True
    assert result.strategy_used == NextcloudStrategy.API
    assert "Scan triggered" in result.output
    mock_httpx_client.post.assert_awaited_once()
    call_args = mock_httpx_client.post.await_args
    assert "cloud.example.com" in call_args[0][0]
    headers = call_args[1]["headers"]
    assert headers["OCS-APIRequest"] == "true"
    assert "test_token_abc" in headers["Authorization"]


@pytest.mark.asyncio
async def test_trigger_occ_api_rescan_all(mock_httpx_client):
    """Verify API strategy sends all=true payload."""
    mock_response = httpx.Response(status_code=200, text="All scanned")
    mock_httpx_client.post.return_value = mock_response

    client = NextcloudClient(
        nextcloud_url="https://cloud.example.com",
        http_client=mock_httpx_client,
    )

    result = await client.trigger_occ_scan(rescan_all=True, strategy=NextcloudStrategy.API)
    assert result.success is True
    call_args = mock_httpx_client.post.await_args
    assert call_args[1]["json"]["all"] == "true"


@pytest.mark.asyncio
async def test_trigger_occ_api_with_internal_client():
    """Verify API strategy creates and closes internal httpx client when not provided."""
    client = NextcloudClient(nextcloud_url="https://cloud.example.com")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("httpx.AsyncClient.aclose", new_callable=AsyncMock) as mock_close:
        mock_post.return_value = httpx.Response(status_code=200, text="OK")

        result = await client.trigger_occ_scan(strategy=NextcloudStrategy.API)
        assert result.success is True
        mock_post.assert_awaited_once()
        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_occ_api_http_error(mock_httpx_client):
    """Verify API strategy handles HTTP errors gracefully."""
    mock_response = httpx.Response(
        status_code=401,
        text="Unauthorized",
    )
    mock_httpx_client.post.return_value = mock_response

    client = NextcloudClient(
        nextcloud_url="https://cloud.example.com",
        nextcloud_token="bad_token",
        http_client=mock_httpx_client,
    )

    result = await client.trigger_occ_scan(
        strategy=NextcloudStrategy.API,
    )

    assert result.success is False
    assert result.strategy_used == NextcloudStrategy.API
    assert "401" in result.error


@pytest.mark.asyncio
async def test_trigger_occ_api_network_error(mock_httpx_client):
    """Verify API strategy handles network exceptions gracefully."""
    mock_httpx_client.post.side_effect = httpx.ConnectError("Connection refused")

    client = NextcloudClient(
        nextcloud_url="https://cloud.example.com",
        http_client=mock_httpx_client,
    )

    result = await client.trigger_occ_scan(
        strategy=NextcloudStrategy.API,
    )

    assert result.success is False
    assert result.strategy_used == NextcloudStrategy.API
    assert "Connection refused" in result.error


# --- Strategy Auto-Detection & Fallback Tests ---

@pytest.mark.asyncio
async def test_trigger_occ_auto_detect_custom_command():
    """Verify auto-detect chooses CUSTOM_COMMAND when nextcloud_occ_command is present."""
    client = NextcloudClient(nextcloud_occ_command="occ files:scan")
    with patch.object(client, "_scan_via_custom_command", new_callable=AsyncMock) as mock_m:
        mock_m.return_value = OccScanResult(success=True, output="ok", strategy_used=NextcloudStrategy.CUSTOM_COMMAND)
        res = await client.trigger_occ_scan()
        assert res.success is True
        mock_m.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_occ_auto_detect_api():
    """Verify auto-detect chooses API when nextcloud_url is present and no occ command."""
    client = NextcloudClient(nextcloud_url="https://cloud.example.com")
    with patch.object(client, "_scan_via_api", new_callable=AsyncMock) as mock_m:
        mock_m.return_value = OccScanResult(success=True, output="ok", strategy_used=NextcloudStrategy.API)
        res = await client.trigger_occ_scan()
        assert res.success is True
        mock_m.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_occ_auto_detect_docker():
    """Verify auto-detect chooses DOCKER_EXEC when docker is configured."""
    client = NextcloudClient(
        nextcloud_url="",
        nextcloud_occ_command="",
        docker_container_name="nextcloud",
        auto_detect_docker=True,
    )
    with patch.object(client, "_scan_via_docker_exec", new_callable=AsyncMock) as mock_m:
        mock_m.return_value = OccScanResult(success=True, output="ok", strategy_used=NextcloudStrategy.DOCKER_EXEC)
        res = await client.trigger_occ_scan()
        assert res.success is True
        mock_m.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_occ_no_configuration():
    """Verify trigger_occ_scan gracefully skips when no Nextcloud strategy is configured."""
    client = NextcloudClient(
        nextcloud_url="",
        nextcloud_occ_command="",
        docker_container_name="",
        docker_socket_path="/nonexistent/docker.sock",
        auto_detect_docker=False,
    )
    result = await client.trigger_occ_scan()
    assert result.success is True
    assert result.strategy_used == NextcloudStrategy.NONE
    assert "skipped" in result.output.lower()


# --- Exception and Timeout Tests ---

@pytest.mark.asyncio
async def test_trigger_occ_subprocess_timeout():
    """Verify subprocess execution timeout is handled gracefully."""
    client = NextcloudClient(nextcloud_occ_command="sleep 100", timeout=0.01)

    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()

    with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
        result = await client.trigger_occ_scan()
        assert result.success is False
        assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_trigger_occ_binary_not_found():
    """Verify FileNotFoundError (e.g. docker binary not found) is handled gracefully."""
    client = NextcloudClient(docker_container_name="nc")

    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("docker not found")):
        result = await client.trigger_occ_scan(strategy=NextcloudStrategy.DOCKER_EXEC)
        assert result.success is False
        assert "not found" in result.error.lower()


# --- Standalone Module Function Test ---

@pytest.mark.asyncio
async def test_module_trigger_occ_scan():
    """Verify module-level standalone trigger_occ_scan function works."""
    with patch("apkpipe.integrations.nextcloud.NextcloudClient.trigger_occ_scan", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = OccScanResult(
            success=True, output="Scanned", strategy_used=NextcloudStrategy.CUSTOM_COMMAND
        )
        res = await trigger_occ_scan(path="/data/downloads/App.apk", user="admin")
        assert res.success is True
        mock_scan.assert_awaited_once_with(path="/data/downloads/App.apk", user="admin", rescan_all=False)
