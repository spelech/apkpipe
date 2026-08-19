"""JDownloader 2 connector via folder watch (.crawljob) and MyJDownloader API (Tier 2)."""

import hashlib
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union
import urllib.parse
import uuid
import httpx

from apkpipe.config import get_settings
from apkpipe.resolvers.base import (
    AuthenticationError,
    BaseResolver,
    ResolvedDownload,
    ResolverError,
)

logger = logging.getLogger(__name__)


class JDownloaderResolver(BaseResolver):
    """Tier 2 Resolver integrating with headless JDownloader 2 via watch folder or API."""

    name: str = "jdownloader"
    tier_name: str = "jdownloader"

    def __init__(
        self,
        watch_dir: Optional[Union[str, Path]] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        device_name: Optional[str] = None,
        api_url: str = "https://api.jdownloader.org",
        timeout: float = 30.0,
    ) -> None:
        """Initialize JDownloaderResolver with watch directory or API credentials."""
        settings = get_settings()

        if watch_dir is not None:
            self.watch_dir: Optional[Path] = Path(watch_dir) if str(watch_dir).strip() else None
        else:
            jd_watch = getattr(settings, "jdownloader_watch_dir", "")
            self.watch_dir = Path(jd_watch) if jd_watch and str(jd_watch).strip() else None

        self.email = email if email is not None else settings.jdownloader_email
        self.password = password if password is not None else settings.jdownloader_password
        self.device_name = device_name if device_name is not None else settings.jdownloader_device_name
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Return True if watch folder is specified or API credentials are provided."""
        has_watch = self.watch_dir is not None and str(self.watch_dir).strip() != ""
        has_api = bool(self.email and self.password)
        return has_watch or has_api

    async def can_resolve(self, link: str) -> bool:
        """Check if JDownloader resolver is configured and can handle the given link."""
        if not self.is_configured:
            return False

        if not link or not (link.startswith(("http://", "https://", "magnet:"))):
            return False

        return True

    def create_crawljob(
        self,
        link: str,
        package_name: Optional[str] = None,
        download_dir: Optional[str] = None,
        filename: Optional[str] = None,
        auto_start: bool = True,
        auto_confirm: bool = True,
        enabled: bool = True,
        **kwargs: Any,
    ) -> Path:
        """Write a JDownloader .crawljob file to the watch folder atomically."""
        if not self.watch_dir:
            raise ResolverError("Watch directory is not configured for JDownloader")

        self.watch_dir.mkdir(parents=True, exist_ok=True)

        lines: List[str] = [
            f"text={link}",
            f"autoStart={'TRUE' if auto_start else 'FALSE'}",
            f"autoConfirm={'TRUE' if auto_confirm else 'FALSE'}",
            f"enabled={'TRUE' if enabled else 'FALSE'}",
        ]

        if package_name:
            lines.append(f"packageName={package_name}")
        if download_dir:
            lines.append(f"downloadFolder={download_dir}")
        if filename:
            lines.append(f"filename={filename}")

        for k, v in kwargs.items():
            if v is not None:
                lines.append(f"{k}={v}")

        content = "\n".join(lines) + "\n"

        unique_id = uuid.uuid4().hex[:8]
        safe_prefix = (package_name or "job").replace(" ", "_").replace("/", "_")
        job_filename = f"{safe_prefix}_{unique_id}.crawljob"
        job_path = self.watch_dir / job_filename

        # Write file atomically via temp file
        temp_path = self.watch_dir / f".tmp_{job_filename}"
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(job_path)

        logger.info("Created JDownloader crawljob at %s", job_path)
        return job_path

    async def _resolve_via_api(
        self,
        link: str,
        package_name: Optional[str] = None,
        download_dir: Optional[str] = None,
        filename: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Submit links to JDownloader instance via MyJDownloader API protocol."""
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            # 1. Connect / Authenticate
            connect_url = f"{self.api_url}/my/connect"
            auth_payload = {
                "email": self.email,
                "password": self.password,
            }
            conn_resp = await client.post(connect_url, json=auth_payload)
            if conn_resp.status_code in (401, 403):
                raise AuthenticationError(f"MyJDownloader authentication failed: {conn_resp.text}")
            conn_resp.raise_for_status()
            conn_data = conn_resp.json()

            session_token = ""
            if isinstance(conn_data, dict):
                session_token = conn_data.get("data", {}).get("sessiontoken", "")

            # 2. List Devices to find device_id
            devices_url = f"{self.api_url}/my/listdevices"
            dev_resp = await client.post(
                devices_url,
                json={"sessiontoken": session_token},
            )
            dev_resp.raise_for_status()
            dev_data = dev_resp.json()

            device_id = None
            device_list = dev_data.get("data", {}).get("list", []) if isinstance(dev_data, dict) else []
            for dev in device_list:
                if not self.device_name or dev.get("name") == self.device_name:
                    device_id = dev.get("id")
                    break

            if not device_id and device_list:
                device_id = device_list[0].get("id")

            # 3. Add link to linkgrabber
            add_url = f"{self.api_url}/t_{session_token}_{device_id}/linkgrabberv2/addLinks"
            add_payload = {
                "links": link,
                "packageName": package_name or "",
                "downloadFolder": download_dir or "",
                "autostart": True,
            }
            add_resp = await client.post(add_url, json=add_payload)
            add_resp.raise_for_status()
            add_result = add_resp.json()

            return {
                "method": "api",
                "device_id": device_id,
                "session_token": session_token,
                "result": add_result,
            }

        except AuthenticationError:
            raise
        except httpx.HTTPError as exc:
            logger.error("HTTP error connecting to MyJDownloader: %s", exc)
            raise ResolverError(f"MyJDownloader API error: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def resolve(
        self,
        link: str,
        package_name: Optional[str] = None,
        download_dir: Optional[str] = None,
        filename: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs: Any,
    ) -> Optional[ResolvedDownload]:
        """Resolve link by submitting to JDownloader watch folder or MyJDownloader API."""
        if not self.is_configured:
            logger.debug("JDownloader resolver skipped: not configured")
            return None

        # Extract hoster from URL
        try:
            parsed = urllib.parse.urlparse(link)
            hoster = parsed.hostname or ""
        except Exception:
            hoster = ""

        # Default download directory from settings if not specified
        if not download_dir:
            settings = get_settings()
            download_dir = settings.download_dir

        resolved_filename = filename or package_name or ""

        # Priority 1: Watch directory (.crawljob file) if configured
        if self.watch_dir is not None:
            try:
                job_path = self.create_crawljob(
                    link=link,
                    package_name=package_name,
                    download_dir=download_dir,
                    filename=filename,
                    **kwargs,
                )
                return ResolvedDownload(
                    download_url=link,
                    original_link=link,
                    filename=resolved_filename,
                    filesize=0,
                    hoster=hoster,
                    tier=self.tier_name,
                    metadata={
                        "method": "crawljob",
                        "crawljob_path": str(job_path),
                        "package_name": package_name,
                        "download_dir": download_dir,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to create crawljob: %s", exc)
                # If API credentials also available, fallback to API
                if not (self.email and self.password):
                    raise ResolverError(f"Failed to submit crawljob: {exc}") from exc

        # Priority 2: MyJDownloader API
        if self.email and self.password:
            api_meta = await self._resolve_via_api(
                link=link,
                package_name=package_name,
                download_dir=download_dir,
                filename=filename,
                client=client,
                **kwargs,
            )
            return ResolvedDownload(
                download_url=link,
                original_link=link,
                filename=resolved_filename,
                filesize=0,
                hoster=hoster,
                tier=self.tier_name,
                metadata={
                    "method": "api",
                    "device_name": self.device_name,
                    "device_id": api_meta.get("device_id"),
                    "package_name": package_name,
                    "download_dir": download_dir,
                    "api_result": api_meta.get("result"),
                },
            )

        return None
