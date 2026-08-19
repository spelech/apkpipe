"""Unit tests for the download engine and streaming downloader."""

import asyncio
from pathlib import Path
from unittest.mock import patch
import pytest
import httpx

from apkpipe.downloader.engine import (
    DownloadEngine,
    DownloadError,
    DownloadProgress,
    DownloadTimeoutError,
)
from apkpipe.resolvers.base import ResolvedDownload


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Fixture providing a temporary directory."""
    d = tmp_path / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def staging_dir(tmp_path: Path) -> Path:
    """Fixture providing a staging directory."""
    d = tmp_path / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_download_progress_defaults():
    """Test DownloadProgress dataclass default values and percent calculation."""
    p = DownloadProgress()
    assert p.downloaded_bytes == 0
    assert p.total_bytes is None
    assert p.speed_bytes_sec == 0.0
    assert p.progress_percent == 0.0
    assert p.status == "pending"


@pytest.mark.asyncio
async def test_download_direct_success(temp_dir: Path, staging_dir: Path):
    """Test successful direct streaming download with progress callbacks."""
    test_content = b"Mock APK file content for download testing " * 1024  # ~44KB
    total_size = len(test_content)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Length": str(total_size)},
            content=test_content,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir, chunk_size=4096)
        dest_file = temp_dir / "sample.apk"

        progress_updates = []

        def on_progress(p: DownloadProgress):
            progress_updates.append(p)

        result_path = await engine.download(
            url_or_resolved="https://example.com/sample.apk",
            destination=dest_file,
            progress_callback=on_progress,
        )

        assert result_path == dest_file
        assert result_path.exists()
        assert result_path.read_bytes() == test_content
        assert len(progress_updates) > 0
        assert progress_updates[-1].status == "completed"
        assert progress_updates[-1].downloaded_bytes == total_size
        assert progress_updates[-1].progress_percent == 100.0


@pytest.mark.asyncio
async def test_download_async_progress_callback(temp_dir: Path, staging_dir: Path):
    """Test download with an async coroutine progress callback."""
    test_content = b"Async callback test content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=test_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        dest_file = temp_dir / "async_cb.apk"

        async_updates = []

        async def async_on_progress(p: DownloadProgress):
            await asyncio.sleep(0.001)
            async_updates.append(p)

        result = await engine.download(
            url_or_resolved="https://example.com/async.apk",
            destination=dest_file,
            progress_callback=async_on_progress,
        )
        assert result == dest_file
        assert len(async_updates) > 0
        assert async_updates[-1].status == "completed"


@pytest.mark.asyncio
async def test_download_progress_callback_exception_handled(temp_dir: Path, staging_dir: Path):
    """Test that exceptions raised inside progress_callback do not fail the download."""
    test_content = b"Content with failing progress callback"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=test_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        dest_file = temp_dir / "cb_fail.apk"

        def faulty_callback(p: DownloadProgress):
            raise RuntimeError("Callback crash")

        result = await engine.download(
            url_or_resolved="https://example.com/cb_fail.apk",
            destination=dest_file,
            progress_callback=faulty_callback,
        )
        assert result == dest_file
        assert result.read_bytes() == test_content


@pytest.mark.asyncio
async def test_download_with_resolved_download_and_dir_destination(temp_dir: Path, staging_dir: Path):
    """Test downloading using ResolvedDownload object where destination is a directory."""
    test_content = b"APK content from resolved download"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Length": str(len(test_content))},
            content=test_content,
        )

    resolved = ResolvedDownload(
        download_url="https://caching.real-debrid.com/d/xyz/Nova_Launcher.apk",
        original_link="https://rapidgator.net/file/123/Nova.apk",
        filename="Nova_Launcher.apk",
        filesize=len(test_content),
        tier="real_debrid",
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download(resolved, destination=temp_dir)

        expected_dest = temp_dir / "Nova_Launcher.apk"
        assert result == expected_dest
        assert result.exists()
        assert result.read_bytes() == test_content


@pytest.mark.asyncio
async def test_download_directory_destination_url_fallback(temp_dir: Path, staging_dir: Path):
    """Test directory destination when URL has empty filename falls back to download.bin."""
    test_content = b"Fallback download"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=test_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download("https://example.com/", destination=temp_dir)
        assert result == temp_dir / "download.bin"
        assert result.read_bytes() == test_content


@pytest.mark.asyncio
async def test_download_no_staging_dir_uses_destination_parent(temp_dir: Path):
    """Test downloading when staging_dir is None uses dest_path.part."""
    test_content = b"No staging dir content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=test_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=None)
        engine.staging_dir = None
        dest_file = temp_dir / "nostaging.apk"
        result = await engine.download("https://example.com/nostaging.apk", destination=dest_file)
        assert result == dest_file
        assert result.read_bytes() == test_content


@pytest.mark.asyncio
async def test_download_overwrites_existing_file(temp_dir: Path, staging_dir: Path):
    """Test downloading overwrites destination file if it already exists."""
    dest_file = temp_dir / "existing.apk"
    dest_file.write_bytes(b"Old file content")
    new_content = b"Brand new content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=new_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download("https://example.com/existing.apk", destination=dest_file)
        assert result.read_bytes() == new_content


@pytest.mark.asyncio
async def test_download_resume_partial_content(temp_dir: Path, staging_dir: Path):
    """Test resuming an interrupted download when server supports HTTP 206."""
    full_content = b"Part1Part2Part3Part4"
    part1 = b"Part1"
    part2 = b"Part2Part3Part4"

    dest_file = temp_dir / "resumed.apk"
    temp_download_file = staging_dir / "resumed.apk.part"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_download_file.write_bytes(part1)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "range" in request.headers
        assert request.headers["range"] == f"bytes={len(part1)}-"
        return httpx.Response(
            status_code=206,
            headers={
                "Content-Range": f"bytes {len(part1)}-{len(full_content)-1}/{len(full_content)}",
                "Content-Length": str(len(part2)),
            },
            content=part2,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download(
            "https://example.com/resumed.apk",
            destination=dest_file,
            resume=True,
        )
        assert result.exists()
        assert result.read_bytes() == full_content


@pytest.mark.asyncio
async def test_download_resume_invalid_content_range_header(temp_dir: Path, staging_dir: Path):
    """Test 206 response with malformed Content-Range header falls back to Content-Length."""
    part1 = b"ABC"
    part2 = b"DEF"
    dest_file = temp_dir / "malformed_range.apk"
    temp_download_file = staging_dir / "malformed_range.apk.part"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_download_file.write_bytes(part1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=206,
            headers={
                "Content-Range": "bytes 3-5/unknown",
                "Content-Length": str(len(part2)),
            },
            content=part2,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download(
            "https://example.com/malformed.apk",
            destination=dest_file,
            resume=True,
        )
        assert result.read_bytes() == b"ABCDEF"


@pytest.mark.asyncio
async def test_download_resume_416_resets_and_retries(temp_dir: Path, staging_dir: Path):
    """Test that HTTP 416 (Range Not Satisfiable) clears partial file and restarts cleanly."""
    full_content = b"FullFreshContent"
    dest_file = temp_dir / "range_416.apk"
    temp_part = staging_dir / "range_416.apk.part"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_part.write_bytes(b"TooLongBytesExceedingFileSize")

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if "Range" in request.headers and call_count == 1:
            return httpx.Response(status_code=416, text="Range Not Satisfiable")
        return httpx.Response(status_code=200, content=full_content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download(
            "https://example.com/range_416.apk",
            destination=dest_file,
            resume=True,
        )
        assert result.read_bytes() == full_content
        assert call_count == 2


@pytest.mark.asyncio
async def test_download_resume_server_returns_200_restarts(temp_dir: Path, staging_dir: Path):
    """Test resuming when server does not support Range and returns 200 OK (restarts download)."""
    full_content = b"FullContentRestarted"
    dest_file = temp_dir / "restart.apk"
    temp_part = staging_dir / "restart.apk.part"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_part.write_bytes(b"OldCorruptedPartial")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"Content-Length": str(len(full_content))},
            content=full_content,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir)
        result = await engine.download(
            "https://example.com/restart.apk",
            destination=dest_file,
            resume=True,
        )
        assert result.read_bytes() == full_content


@pytest.mark.asyncio
async def test_download_retry_on_network_error(temp_dir: Path, staging_dir: Path):
    """Test retry mechanism on transient network failure before success."""
    attempts = 0
    content = b"Retry success data"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ConnectError("Network blip", request=request)
        return httpx.Response(status_code=200, content=content)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(
            client=client,
            staging_dir=staging_dir,
            max_retries=3,
            retry_delay=0.01,
        )
        dest = temp_dir / "retried.apk"
        result = await engine.download("https://example.com/retry.apk", destination=dest)
        assert result.read_bytes() == content
        assert attempts == 2


@pytest.mark.asyncio
async def test_download_retry_exhausted_raises_error(temp_dir: Path, staging_dir: Path):
    """Test that exhausting retries raises DownloadError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(
            client=client,
            staging_dir=staging_dir,
            max_retries=2,
            retry_delay=0.01,
        )
        with pytest.raises(DownloadError):
            await engine.download("https://example.com/fail.apk", destination=temp_dir / "fail.apk")


@pytest.mark.asyncio
async def test_download_http_error_raises_download_error(temp_dir: Path, staging_dir: Path):
    """Test that HTTP 404/500 errors raise DownloadError without endless retries."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404, text="Not Found")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        engine = DownloadEngine(client=client, staging_dir=staging_dir, max_retries=1)
        with pytest.raises(DownloadError) as exc_info:
            await engine.download("https://example.com/notfound.apk", destination=temp_dir / "nf.apk")
        assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_engine_context_manager(temp_dir: Path, staging_dir: Path):
    """Test DownloadEngine async context manager lifecycle."""
    test_content = b"Context manager test"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=test_content)

    transport = httpx.MockTransport(handler)
    mock_client = httpx.AsyncClient(transport=transport)

    with patch("apkpipe.downloader.engine.httpx.AsyncClient", return_value=mock_client):
        async with DownloadEngine(staging_dir=staging_dir) as engine:
            assert engine._client is not None
            client = engine._get_client()
            assert client is not None
            dest = temp_dir / "cm.apk"
            res = await engine.download("https://example.com/cm.apk", destination=dest)
            assert res.read_bytes() == test_content

        assert engine._client is None


@pytest.mark.asyncio
async def test_download_engine_unhandled_exception_wrapped(temp_dir: Path, staging_dir: Path):
    """Test unexpected exception during download is wrapped into DownloadError."""
    engine = DownloadEngine(staging_dir=staging_dir)

    with patch.object(engine, "_resolve_target_path", side_effect=Exception("Disk format corrupted")):
        with pytest.raises(DownloadError, match="Unexpected download error"):
            await engine.download("https://example.com/error.apk", destination=temp_dir / "err.apk")
