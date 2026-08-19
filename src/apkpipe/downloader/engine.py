"""Async streaming file download engine with resume support and progress callbacks."""

import asyncio
from dataclasses import dataclass
import inspect
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union
import urllib.parse

import httpx

from apkpipe.config import get_settings
from apkpipe.resolvers.base import ResolvedDownload

logger = logging.getLogger(__name__)

ProgressCallback = Callable[["DownloadProgress"], Union[None, Awaitable[None]]]


@dataclass
class DownloadProgress:
    """Represents current state and metrics for an active or completed download."""

    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed_bytes_sec: float = 0.0
    progress_percent: float = 0.0
    status: str = "pending"


class DownloadError(Exception):
    """Base exception for file download errors."""


class DownloadTimeoutError(DownloadError):
    """Raised when a download operation times out."""


class DownloadHTTPError(DownloadError):
    """Raised when an HTTP error status code is encountered during download."""


class DownloadEngine:
    """High-performance async streaming download engine with resume and retry support."""

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 60.0,
        chunk_size: int = 65536,  # 64 KB
        max_retries: int = 3,
        retry_delay: float = 1.0,
        staging_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize DownloadEngine.

        Args:
            client: Optional shared httpx.AsyncClient.
            timeout: HTTP request timeout in seconds.
            chunk_size: Chunk size in bytes for stream reads.
            max_retries: Maximum number of retry attempts on network errors.
            retry_delay: Base delay between retries in seconds.
            staging_dir: Optional staging directory for temporary .part files.
        """
        self._client = client
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if staging_dir is not None:
            self.staging_dir = Path(staging_dir)
        else:
            settings_staging = get_settings().staging_dir
            self.staging_dir = Path(settings_staging) if settings_staging else None

    async def __aenter__(self) -> "DownloadEngine":
        """Async context manager enter."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0), follow_redirects=True)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        # Only close client if created internally during context management
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return the active HTTP client or create a temporary one."""
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0), follow_redirects=True)

    def _resolve_target_path(
        self,
        url: str,
        destination: Union[str, Path],
        resolved_download: Optional[ResolvedDownload] = None,
    ) -> Path:
        """Resolve final target file path given destination and download context."""
        dest = Path(destination)
        if dest.is_dir() or str(destination).endswith(("/", "\\")):
            filename = ""
            if resolved_download and resolved_download.filename:
                filename = resolved_download.filename
            else:
                parsed = urllib.parse.urlparse(url)
                filename = Path(parsed.path).name
            if not filename:
                filename = "download.bin"
            return dest / filename
        return dest

    async def _emit_progress(
        self,
        callback: Optional[ProgressCallback],
        progress: DownloadProgress,
    ) -> None:
        """Safely invoke sync or async progress callback."""
        if not callback:
            return
        try:
            res = callback(progress)
            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            logger.debug("Progress callback exception: %s", exc)

    async def download(
        self,
        url_or_resolved: Union[str, ResolvedDownload],
        destination: Union[str, Path],
        progress_callback: Optional[ProgressCallback] = None,
        resume: bool = True,
        headers: Optional[Dict[str, str]] = None,
    ) -> Path:
        """Stream a file from remote URL to local destination with resume and retry support.

        Args:
            url_or_resolved: Direct download URL or ResolvedDownload object.
            destination: Target file path or directory.
            progress_callback: Optional callback receiving DownloadProgress updates.
            resume: Whether to attempt resuming partially downloaded files.
            headers: Optional HTTP headers.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadError: On unrecoverable download or HTTP failure.
        """
        client_created = False
        try:
            if isinstance(url_or_resolved, ResolvedDownload):
                url = url_or_resolved.download_url
                resolved_obj = url_or_resolved
            else:
                url = str(url_or_resolved)
                resolved_obj = None

            dest_path = self._resolve_target_path(url, destination, resolved_obj)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if self.staging_dir:
                self.staging_dir.mkdir(parents=True, exist_ok=True)
                temp_part_path = self.staging_dir / f"{dest_path.name}.part"
            else:
                temp_part_path = dest_path.with_suffix(dest_path.suffix + ".part")
                temp_part_path.parent.mkdir(parents=True, exist_ok=True)

            client = self._client
            if client is None:
                client = httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=30.0), follow_redirects=True)
                client_created = True
        except Exception as exc:
            if not isinstance(exc, DownloadError):
                logger.exception("Unexpected error preparing download for %s: %s", url_or_resolved, exc)
                raise DownloadError(f"Unexpected download error: {exc}") from exc
            raise

        try:
            attempts = 0
            while attempts <= self.max_retries:
                attempts += 1
                try:
                    req_headers = dict(headers or {})
                    existing_bytes = 0
                    if resume and temp_part_path.exists():
                        existing_bytes = temp_part_path.stat().st_size
                        if existing_bytes > 0:
                            req_headers["Range"] = f"bytes={existing_bytes}-"

                    req = client.build_request("GET", url, headers=req_headers)
                    resp = await client.send(req, stream=True)
                    try:
                        if resp.status_code == 416 and existing_bytes > 0:
                            # Range not satisfiable, restart from beginning
                            await resp.aclose()
                            if temp_part_path.exists():
                                temp_part_path.unlink()
                            existing_bytes = 0
                            req_headers.pop("Range", None)
                            req = client.build_request("GET", url, headers=req_headers)
                            resp = await client.send(req, stream=True)

                        if resp.status_code not in (200, 206):
                            error_text = await resp.aread()
                            raise DownloadHTTPError(
                                f"HTTP {resp.status_code} while downloading {url}: {error_text.decode('utf-8', errors='ignore')[:200]}"
                            )

                        # Determine total size
                        total_bytes: Optional[int] = None
                        file_mode = "wb"
                        downloaded_bytes = 0

                        if resp.status_code == 206:
                            file_mode = "ab"
                            downloaded_bytes = existing_bytes
                            content_range = resp.headers.get("Content-Range", "")
                            if "/" in content_range:
                                try:
                                    total_bytes = int(content_range.split("/")[-1])
                                except ValueError:
                                    total_bytes = None
                            if total_bytes is None:
                                cl = resp.headers.get("Content-Length")
                                if cl and cl.isdigit():
                                    total_bytes = existing_bytes + int(cl)
                        else:
                            # HTTP 200: full file stream
                            file_mode = "wb"
                            downloaded_bytes = 0
                            cl = resp.headers.get("Content-Length")
                            if cl and cl.isdigit():
                                total_bytes = int(cl)

                        start_time = time.monotonic()
                        bytes_this_session = 0

                        progress = DownloadProgress(
                            downloaded_bytes=downloaded_bytes,
                            total_bytes=total_bytes,
                            speed_bytes_sec=0.0,
                            progress_percent=(downloaded_bytes / total_bytes * 100.0) if (total_bytes and total_bytes > 0) else 0.0,
                            status="downloading",
                        )
                        await self._emit_progress(progress_callback, progress)

                        with open(temp_part_path, file_mode) as f:
                            async for chunk in resp.aiter_bytes(chunk_size=self.chunk_size):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_bytes += len(chunk)
                                    bytes_this_session += len(chunk)

                                    elapsed = time.monotonic() - start_time
                                    speed = (bytes_this_session / elapsed) if elapsed > 0 else 0.0
                                    percent = (downloaded_bytes / total_bytes * 100.0) if (total_bytes and total_bytes > 0) else 0.0

                                    progress.downloaded_bytes = downloaded_bytes
                                    progress.speed_bytes_sec = speed
                                    progress.progress_percent = min(percent, 100.0)
                                    progress.status = "downloading"
                                    await self._emit_progress(progress_callback, progress)
                    finally:
                        await resp.aclose()

                    # Atomic rename/move to destination
                    if dest_path.exists():
                        dest_path.unlink()
                    shutil.move(str(temp_part_path), str(dest_path))

                    # Final completion event
                    progress.downloaded_bytes = downloaded_bytes
                    progress.progress_percent = 100.0
                    progress.status = "completed"
                    await self._emit_progress(progress_callback, progress)

                    logger.info("Downloaded %s to %s (%d bytes)", url, dest_path, downloaded_bytes)
                    return dest_path

                except DownloadHTTPError:
                    raise
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    logger.warning(
                        "Download error attempt %d/%d for %s: %s",
                        attempts,
                        self.max_retries + 1,
                        url,
                        exc,
                    )
                    if attempts > self.max_retries:
                        raise DownloadError(f"Failed to download {url} after {attempts} attempts: {exc}") from exc
                    await asyncio.sleep(self.retry_delay * attempts)
                except Exception as exc:
                    logger.exception("Unexpected error downloading %s: %s", url, exc)
                    raise DownloadError(f"Unexpected download error: {exc}") from exc

            raise DownloadError(f"Failed to download {url} after max retries")

        finally:
            if client_created:
                await client.aclose()

