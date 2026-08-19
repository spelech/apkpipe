"""Nextcloud integration client for triggering OCC file scans and webhook indexing."""

import asyncio
from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
import re
import time
from typing import Optional, Tuple, Union
import httpx

from apkpipe.config import get_settings

logger = logging.getLogger(__name__)

# Matches Nextcloud OCC files:scan table row e.g. | 4 | 18 | 00:00:03 |
OCC_SUMMARY_TABLE_RE = re.compile(r'\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*[\d:]+\s*\|')


class NextcloudStrategy(str, Enum):
    """Execution strategy for triggering Nextcloud file indexing."""

    CUSTOM_COMMAND = "custom_command"
    DOCKER_EXEC = "docker_exec"
    API = "api"
    NONE = "none"


@dataclass
class OccScanResult:
    """Structured result of a Nextcloud OCC file scan invocation."""

    success: bool
    output: str
    error: Optional[str] = None
    strategy_used: str = NextcloudStrategy.NONE
    execution_time_seconds: float = 0.0
    scanned_files_count: Optional[int] = None
    scanned_folders_count: Optional[int] = None


def format_scan_path(
    path: Union[str, Path],
    base_dir: Optional[Union[str, Path]] = None,
    user: Optional[str] = None,
) -> str:
    """Format filesystem path into Nextcloud-compatible scan path for --path argument.

    Args:
        path: Target file or directory path.
        base_dir: Base download directory to strip if present.
        user: Optional Nextcloud user name (e.g. 'admin').

    Returns:
        Formatted Nextcloud path (e.g. '/admin/files/Spotify/Spotify v8.9.0.apk').
    """
    str_path = str(path)
    base_str = str(base_dir) if base_dir is not None else get_settings().download_dir

    rel_path = str_path
    if base_str and str_path.startswith(base_str):
        rel_path = str_path[len(base_str):]

    clean_rel = rel_path.strip("/")

    if user:
        user_files_prefix = f"{user}/files"
        if not clean_rel.startswith(user_files_prefix):
            clean_rel = f"{user_files_prefix}/{clean_rel}" if clean_rel else user_files_prefix

    return f"/{clean_rel}"


def parse_occ_output(output: str) -> Tuple[Optional[int], Optional[int]]:
    """Parse scanned folders and files counts from standard Nextcloud occ output.

    Args:
        output: Standard output text from occ files:scan.

    Returns:
        Tuple of (folders_count, files_count), or (None, None) if not found.
    """
    if not output:
        return None, None

    match = OCC_SUMMARY_TABLE_RE.search(output)
    if match:
        try:
            folders = int(match.group(1))
            files = int(match.group(2))
            return folders, files
        except (ValueError, IndexError):
            pass

    return None, None


class NextcloudClient:
    """Client for triggering Nextcloud file indexing via Docker, Subprocess, or API."""

    def __init__(
        self,
        nextcloud_url: Optional[str] = None,
        nextcloud_token: Optional[str] = None,
        nextcloud_occ_command: Optional[str] = None,
        docker_container_name: str = "nextcloud",
        docker_user: str = "33",
        docker_socket_path: str = "/var/run/docker.sock",
        auto_detect_docker: bool = True,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 60.0,
    ) -> None:
        """Initialize NextcloudClient.

        Args:
            nextcloud_url: Nextcloud base URL or OCS endpoint.
            nextcloud_token: API token or bearer token for Nextcloud.
            nextcloud_occ_command: Custom shell command to invoke occ (e.g. 'docker exec -u 33 nc php occ files:scan').
            docker_container_name: Target container name for docker exec.
            docker_user: User to run docker exec as (default 33 for www-data).
            docker_socket_path: Path to docker daemon UNIX socket.
            auto_detect_docker: Whether to attempt docker exec if container or socket exists.
            http_client: Optional httpx.AsyncClient instance.
            timeout: Command or request execution timeout in seconds.
        """
        settings = get_settings()
        self.nextcloud_url = (
            nextcloud_url if nextcloud_url is not None else settings.nextcloud_url
        )
        self.nextcloud_token = (
            nextcloud_token if nextcloud_token is not None else settings.nextcloud_token
        )
        self.nextcloud_occ_command = (
            nextcloud_occ_command
            if nextcloud_occ_command is not None
            else settings.nextcloud_occ_command
        )
        self.docker_container_name = docker_container_name
        self.docker_user = docker_user
        self.docker_socket_path = docker_socket_path
        self.auto_detect_docker = auto_detect_docker
        self._external_client = http_client
        self.timeout = timeout

    async def _scan_via_custom_command(
        self,
        path: Optional[Union[str, Path]] = None,
        user: Optional[str] = None,
        rescan_all: bool = False,
    ) -> OccScanResult:
        """Execute custom configured shell command."""
        import shlex
        cmd_args = shlex.split(self.nextcloud_occ_command.strip())

        if rescan_all:
            if "--all" not in cmd_args:
                cmd_args.append("--all")
        elif path is not None:
            scan_path = format_scan_path(path, user=user)
            has_path = any(arg.startswith("--path=") for arg in cmd_args)
            if not has_path:
                cmd_args.append(f"--path={scan_path}")
        elif user is not None:
            if user not in cmd_args:
                cmd_args.append(user)

        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
            elapsed = time.monotonic() - start_time
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                folders, files = parse_occ_output(stdout_str)
                logger.info(
                    "Nextcloud OCC scan succeeded via custom command in %.2fs (folders: %s, files: %s)",
                    elapsed,
                    folders,
                    files,
                )
                return OccScanResult(
                    success=True,
                    output=stdout_str,
                    strategy_used=NextcloudStrategy.CUSTOM_COMMAND,
                    execution_time_seconds=elapsed,
                    scanned_folders_count=folders,
                    scanned_files_count=files,
                )
            else:
                logger.warning(
                    "Nextcloud OCC scan failed (exit %d): %s",
                    proc.returncode,
                    stderr_str or stdout_str,
                )
                return OccScanResult(
                    success=False,
                    output=stdout_str,
                    error=stderr_str or f"Command exited with code {proc.returncode}",
                    strategy_used=NextcloudStrategy.CUSTOM_COMMAND,
                    execution_time_seconds=elapsed,
                )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            logger.warning("Nextcloud OCC command timed out after %.2fs", self.timeout)
            return OccScanResult(
                success=False,
                output="",
                error=f"OCC scan timed out after {self.timeout}s",
                strategy_used=NextcloudStrategy.CUSTOM_COMMAND,
                execution_time_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            logger.warning("Failed to execute OCC custom command: %s", exc)
            return OccScanResult(
                success=False,
                output="",
                error=str(exc),
                strategy_used=NextcloudStrategy.CUSTOM_COMMAND,
                execution_time_seconds=elapsed,
            )

    async def _scan_via_docker_exec(
        self,
        path: Optional[Union[str, Path]] = None,
        user: Optional[str] = None,
        rescan_all: bool = False,
    ) -> OccScanResult:
        """Execute occ files:scan inside target Nextcloud container via docker exec."""
        args = [
            "docker",
            "exec",
            "-u",
            self.docker_user,
            self.docker_container_name,
            "php",
            "occ",
            "files:scan",
        ]

        if rescan_all:
            args.append("--all")
        elif path is not None:
            scan_path = format_scan_path(path, user=user)
            args.append(f"--path={scan_path}")
        elif user is not None:
            args.append(user)

        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
            elapsed = time.monotonic() - start_time
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                folders, files = parse_occ_output(stdout_str)
                logger.info(
                    "Nextcloud OCC scan succeeded via docker exec in %.2fs (folders: %s, files: %s)",
                    elapsed,
                    folders,
                    files,
                )
                return OccScanResult(
                    success=True,
                    output=stdout_str,
                    strategy_used=NextcloudStrategy.DOCKER_EXEC,
                    execution_time_seconds=elapsed,
                    scanned_folders_count=folders,
                    scanned_files_count=files,
                )
            else:
                logger.warning(
                    "Nextcloud OCC docker exec failed (exit %d): %s",
                    proc.returncode,
                    stderr_str or stdout_str,
                )
                return OccScanResult(
                    success=False,
                    output=stdout_str,
                    error=stderr_str or f"Docker exec exited with code {proc.returncode}",
                    strategy_used=NextcloudStrategy.DOCKER_EXEC,
                    execution_time_seconds=elapsed,
                )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            logger.warning("Nextcloud OCC docker exec timed out after %.2fs", self.timeout)
            return OccScanResult(
                success=False,
                output="",
                error=f"OCC docker exec timed out after {self.timeout}s",
                strategy_used=NextcloudStrategy.DOCKER_EXEC,
                execution_time_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start_time
            logger.warning("Failed to execute OCC docker exec: %s", exc)
            return OccScanResult(
                success=False,
                output="",
                error=str(exc),
                strategy_used=NextcloudStrategy.DOCKER_EXEC,
                execution_time_seconds=elapsed,
            )

    async def _scan_via_api(
        self,
        path: Optional[Union[str, Path]] = None,
        user: Optional[str] = None,
        rescan_all: bool = False,
    ) -> OccScanResult:
        """Trigger scan via Nextcloud OCS REST API or webhook."""
        url = f"{self.nextcloud_url.rstrip('/')}/ocs/v2.php/apps/files/api/v1/scan"
        headers = {
            "OCS-APIRequest": "true",
            "Accept": "application/json",
        }
        if self.nextcloud_token:
            headers["Authorization"] = f"Bearer {self.nextcloud_token}"

        payload = {}
        if rescan_all:
            payload["all"] = "true"
        elif path is not None:
            payload["path"] = format_scan_path(path, user=user)
        if user:
            payload["user"] = user

        start_time = time.monotonic()
        client = (
            self._external_client
            if self._external_client is not None
            else httpx.AsyncClient(timeout=self.timeout)
        )
        should_close = self._external_client is None

        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            elapsed = time.monotonic() - start_time
            if response.is_success:
                logger.info("Nextcloud OCC scan triggered via API in %.2fs", elapsed)
                return OccScanResult(
                    success=True,
                    output=response.text,
                    strategy_used=NextcloudStrategy.API,
                    execution_time_seconds=elapsed,
                )
            else:
                logger.warning(
                    "Nextcloud OCC scan via API failed with status %d: %s",
                    response.status_code,
                    response.text,
                )
                return OccScanResult(
                    success=False,
                    output=response.text,
                    error=f"HTTP {response.status_code}: {response.text}",
                    strategy_used=NextcloudStrategy.API,
                    execution_time_seconds=elapsed,
                )
        except (httpx.HTTPError, httpx.RequestError, Exception) as exc:
            elapsed = time.monotonic() - start_time
            logger.warning("Nextcloud OCC scan via API failed: %s", exc)
            return OccScanResult(
                success=False,
                output="",
                error=str(exc),
                strategy_used=NextcloudStrategy.API,
                execution_time_seconds=elapsed,
            )
        finally:
            if should_close:
                await client.aclose()

    async def trigger_occ_scan(
        self,
        path: Optional[Union[str, Path]] = None,
        user: Optional[str] = None,
        rescan_all: bool = False,
        strategy: Optional[str] = None,
    ) -> OccScanResult:
        """Trigger Nextcloud file indexing with automatic strategy selection.

        Args:
            path: Target file or folder path to scan.
            user: Nextcloud username whose files are being scanned.
            rescan_all: If True, rescans all files across Nextcloud.
            strategy: Explicit strategy override (CUSTOM_COMMAND, DOCKER_EXEC, API).

        Returns:
            OccScanResult containing success status, output, and execution details.
        """
        # 1. Handle explicit strategy override
        if strategy == NextcloudStrategy.CUSTOM_COMMAND:
            return await self._scan_via_custom_command(path=path, user=user, rescan_all=rescan_all)
        elif strategy == NextcloudStrategy.DOCKER_EXEC:
            return await self._scan_via_docker_exec(path=path, user=user, rescan_all=rescan_all)
        elif strategy == NextcloudStrategy.API:
            return await self._scan_via_api(path=path, user=user, rescan_all=rescan_all)

        # 2. Auto-detect strategy based on available configuration
        if self.nextcloud_occ_command:
            return await self._scan_via_custom_command(path=path, user=user, rescan_all=rescan_all)
        elif self.nextcloud_url:
            return await self._scan_via_api(path=path, user=user, rescan_all=rescan_all)
        elif self.auto_detect_docker and (
            self.docker_container_name or os.path.exists(self.docker_socket_path)
        ):
            # Check if docker binary exists or if docker_container_name is set
            return await self._scan_via_docker_exec(path=path, user=user, rescan_all=rescan_all)

        # 3. No integration configured
        logger.debug("No Nextcloud integration configured; skipping OCC file scan.")
        return OccScanResult(
            success=True,
            output="Nextcloud OCC scan skipped: no Nextcloud integration configured",
            strategy_used=NextcloudStrategy.NONE,
        )


async def trigger_occ_scan(
    path: Optional[Union[str, Path]] = None,
    user: Optional[str] = None,
    rescan_all: bool = False,
) -> OccScanResult:
    """Global helper function to trigger Nextcloud OCC scan with default client."""
    client = NextcloudClient()
    return await client.trigger_occ_scan(path=path, user=user, rescan_all=rescan_all)
