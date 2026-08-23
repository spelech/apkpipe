"""AllDebrid REST API link resolver (Tier 1b)."""

import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Set
import httpx

from apkpipe.config import get_settings
from apkpipe.resolvers.base import (
    AuthenticationError,
    BaseResolver,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    ResolverError,
    UnsupportedHosterError,
)

logger = logging.getLogger(__name__)

# Default known supported hoster domains for AllDebrid fast local matching
KNOWN_AD_HOSTERS: Set[str] = {
    "rapidgator.net",
    "rg.to",
    "mega.nz",
    "mega.co.nz",
    "katfile.com",
    "dropgalaxy.in",
    "dropgalaxy.com",
    "dropgalaxy.co",
    "uploady.io",
    "uploady.net",
    "uploady.com",
    "1fichier.com",
    "userupload.net",
    "userupload.in",
    "userupload.io",
    "send.cm",
    "sendcm.com",
    "fastupload.io",
    "fastupload.co",
    "dailyuploads.net",
    "dailyuploads.com",
    "ddownload.com",
    "hexupload.net",
    "uploadrar.com",
    "filefactory.com",
    "turbobit.net",
    "nitroflare.com",
    "mediafire.com",
    "uptobox.com",
    "alfafile.net",
    "world-bytez.com",
    "filecondo.com",
    "clicknupload.click",
    "clicknupload.me",
    "clicknupload.org",
    "gofile.io",
    "modsbase.com",
    "share-online.is",
    "wdupload.com",
    "fikper.com",
    "k2s.cc",
    "keep2share.cc",
}


class AllDebridResolver(BaseResolver):
    """Tier 1b Link Resolver using AllDebrid API v4 to unlock hoster links."""

    name: str = "alldebrid"
    tier_name: str = "alldebrid"

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent: str = "apkpipe",
        base_url: str = "https://api.alldebrid.com/v4",
        timeout: float = 30.0,
    ) -> None:
        """Initialize AllDebridResolver with optional key/agent override or fallback to settings."""
        settings = get_settings()
        if api_key is None:
            self.api_key = (
                getattr(settings, "alldebrid_api_key", "")
                or getattr(settings, "all_debrid_api_key", "")
                or ""
            )
        else:
            self.api_key = api_key

        if agent == "apkpipe":
            self.agent = getattr(settings, "alldebrid_agent", "") or agent
        else:
            self.agent = agent

        if not self.agent:
            self.agent = "apkpipe"

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cached_hosts: Optional[List[str]] = None

    @property
    def is_configured(self) -> bool:
        """Return True if an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    async def can_resolve(self, link: str) -> bool:
        """Check if AllDebrid is configured and the domain is supported."""
        if not self.is_configured or not link or not link.startswith(("http://", "https://")):
            return False

        try:
            parsed = urllib.parse.urlparse(link)
            host = (parsed.hostname or "").lower()
            if not host:
                return False

            # Check cached remote hosts if available
            if self._cached_hosts is not None:
                for supported in self._cached_hosts:
                    if host == supported or host.endswith("." + supported):
                        return True

            # Match against known AD hosters list
            for known in KNOWN_AD_HOSTERS:
                if host == known or host.endswith("." + known):
                    return True

            return False
        except Exception:
            return False

    async def get_supported_hosts(
        self, client: Optional[httpx.AsyncClient] = None
    ) -> List[str]:
        """Fetch list of supported operational hosters from AllDebrid /hosts."""
        if not self.is_configured:
            return []

        url = f"{self.base_url}/hosts"
        params: Dict[str, Any] = {"agent": self.agent, "apikey": self.api_key}
        headers = {"Authorization": f"Bearer {self.api_key}"}

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code in (401, 403):
                raise AuthenticationError("Invalid or expired AllDebrid API key")
            response.raise_for_status()

            data = response.json()
            active_hosts: List[str] = []
            if isinstance(data, dict):
                hosts_data = (
                    data.get("data", {}).get("hosts", {})
                    if "data" in data
                    else data.get("hosts", {})
                )
                if isinstance(hosts_data, dict):
                    for host_key, host_info in hosts_data.items():
                        if isinstance(host_info, dict):
                            if host_info.get("status", True):
                                domains = host_info.get("domains")
                                if isinstance(domains, list) and domains:
                                    active_hosts.extend(domains)
                                elif "domain" in host_info and host_info["domain"]:
                                    active_hosts.append(host_info["domain"])
                                else:
                                    active_hosts.append(host_key)
                        elif isinstance(host_info, (str, bool)) and host_info:
                            active_hosts.append(host_key)
                elif isinstance(hosts_data, list):
                    for item in hosts_data:
                        if isinstance(item, str):
                            active_hosts.append(item)
                        elif isinstance(item, dict) and "domain" in item:
                            active_hosts.append(item["domain"])

            self._cached_hosts = active_hosts
            return active_hosts
        except httpx.HTTPError as exc:
            logger.error("Failed to query AllDebrid supported hosts: %s", exc)
            raise ResolverError(f"Failed to query supported hosts: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def resolve(
        self,
        link: str,
        password: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs: Any,
    ) -> Optional[ResolvedDownload]:
        """Unlock a hoster link using AllDebrid /link/unlock."""
        if not self.is_configured:
            logger.debug("AllDebrid resolver skipped: no API key configured")
            return None

        url = f"{self.base_url}/link/unlock"
        params: Dict[str, Any] = {
            "agent": self.agent,
            "apikey": self.api_key,
            "link": link,
        }
        if password:
            params["password"] = password

        headers = {"Authorization": f"Bearer {self.api_key}"}

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            response = await client.get(url, params=params, headers=headers)
            status = response.status_code

            # Handle HTTP auth errors
            if status in (401, 403):
                raise AuthenticationError(
                    f"AllDebrid authentication failed ({status}): {response.text}"
                )

            # Handle HTTP rate limit
            if status == 429:
                raise RateLimitError("AllDebrid API rate limit reached (429)")

            try:
                payload = response.json()
            except Exception:
                payload = {}

            # Handle JSON error responses
            if isinstance(payload, dict) and payload.get("status") == "error":
                err_info = payload.get("error", {})
                if isinstance(err_info, dict):
                    err_code = str(err_info.get("code", "")).upper()
                    err_msg = str(err_info.get("message", ""))
                else:
                    err_code = str(err_info).upper()
                    err_msg = str(err_info)

                full_err = f"{err_code}: {err_msg}" if err_msg else err_code

                if err_code in (
                    "AUTH_BAD_APIKEY",
                    "AUTH_BLOCKED",
                    "AUTH_USER_BANNED",
                    "AUTH_MISSING_APIKEY",
                ):
                    raise AuthenticationError(f"AllDebrid auth error: {full_err}")
                if err_code in ("LINK_DEAD", "LINK_DOWN", "FILE_NOT_FOUND", "LINK_ERROR"):
                    raise LinkDeadError(f"Dead link or file not found: {full_err}")
                if err_code in (
                    "LINK_HOST_NOT_SUPPORTED",
                    "HOST_NOT_AVAILABLE",
                    "LINK_HOST_UNAVAILABLE",
                    "LINK_HOST_FULL",
                    "HOST_UNAVAILABLE",
                    "HOST_DOWN",
                ):
                    raise UnsupportedHosterError(
                        f"Hoster not supported or unavailable: {full_err}"
                    )
                if err_code in (
                    "RATE_LIMITED",
                    "TOO_MANY_REQUESTS",
                    "FREE_TRIAL_LIMIT_REACHED",
                    "LIMIT_REACHED",
                ):
                    raise RateLimitError(f"AllDebrid rate limit: {full_err}")
                if err_code in ("MUST_BE_PREMIUM", "AUTH_MUST_BE_PREMIUM"):
                    raise AuthenticationError(
                        f"AllDebrid account premium required: {full_err}"
                    )

                raise ResolverError(f"AllDebrid error ({err_code}): {err_msg}")

            if status == 404:
                raise LinkDeadError(f"File not found on remote hoster (404): {link}")
            if status >= 400:
                raise ResolverError(
                    f"AllDebrid request failed with status {status}: {response.text}"
                )

            data = payload.get("data", {})
            if not isinstance(data, dict):
                raise ResolverError("AllDebrid response missing data payload")

            download_url = data.get("link", "")
            if not download_url:
                raise ResolverError("AllDebrid response missing download link")

            filename = data.get("filename", "")
            filesize = int(data.get("filesize", 0))
            hoster = data.get("host", "")

            return ResolvedDownload(
                download_url=download_url,
                original_link=link,
                filename=filename,
                filesize=filesize,
                hoster=hoster,
                tier=self.tier_name,
                metadata=data,
            )

        except (
            AuthenticationError,
            RateLimitError,
            UnsupportedHosterError,
            LinkDeadError,
            ResolverError,
        ):
            raise
        except httpx.HTTPError as exc:
            logger.error("HTTP error connecting to AllDebrid: %s", exc)
            raise ResolverError(f"AllDebrid network error: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()
