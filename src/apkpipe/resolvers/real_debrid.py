"""Real-Debrid REST API link resolver (Tier 1)."""

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

# Default known supported hoster domains for Real-Debrid fast local matching
KNOWN_RD_HOSTERS: Set[str] = {
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
    "zippyshare.com",
}


class RealDebridResolver(BaseResolver):
    """Tier 1 Link Resolver using the Real-Debrid API to unrestrict hoster links."""

    name: str = "real_debrid"
    tier_name: str = "real_debrid"

    def __init__(
        self,
        api_token: Optional[str] = None,
        base_url: str = "https://api.real-debrid.com/rest/1.0",
        timeout: float = 30.0,
    ) -> None:
        """Initialize RealDebridResolver with optional token override."""
        if api_token is None:
            settings = get_settings()
            self.api_token = settings.real_debrid_api_token
        else:
            self.api_token = api_token

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cached_hosts: Optional[List[str]] = None

    @property
    def is_configured(self) -> bool:
        """Return True if an API token is present."""
        return bool(self.api_token and self.api_token.strip())

    def _get_headers(self) -> Dict[str, str]:
        """Generate authorization headers for Real-Debrid requests."""
        return {"Authorization": f"Bearer {self.api_token}"}

    async def can_resolve(self, link: str) -> bool:
        """Check if Real-Debrid is configured and the domain is supported."""
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

            # Match against known RD hosters list
            for known in KNOWN_RD_HOSTERS:
                if host == known or host.endswith("." + known):
                    return True

            return False
        except Exception:
            return False

    async def get_supported_hosts(
        self, client: Optional[httpx.AsyncClient] = None
    ) -> List[str]:
        """Fetch list of supported operational hosters from Real-Debrid /hosts/status."""
        if not self.is_configured:
            return []

        url = f"{self.base_url}/hosts/status"
        headers = self._get_headers()

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 401 or response.status_code == 403:
                raise AuthenticationError("Invalid or expired Real-Debrid API token")
            response.raise_for_status()

            data = response.json()
            active_hosts = []
            if isinstance(data, dict):
                for host, status_info in data.items():
                    if isinstance(status_info, dict) and status_info.get("status") == "up":
                        active_hosts.append(host)
                    elif isinstance(status_info, str) and status_info == "up":
                        active_hosts.append(host)
            elif isinstance(data, list):
                active_hosts = data

            self._cached_hosts = active_hosts
            return active_hosts
        except httpx.HTTPError as exc:
            logger.error("Failed to query Real-Debrid supported hosts: %s", exc)
            raise ResolverError(f"Failed to query supported hosts: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def check_link(
        self,
        link: str,
        password: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, Any]:
        """Check link status and hoster support via Real-Debrid /unrestrict/check."""
        if not self.is_configured:
            raise AuthenticationError("Real-Debrid API token is not configured")

        url = f"{self.base_url}/unrestrict/check"
        headers = self._get_headers()
        data: Dict[str, str] = {"link": link}
        if password:
            data["password"] = password

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            response = await client.post(url, headers=headers, data=data)
            if response.status_code in (401, 403):
                raise AuthenticationError("Invalid or expired Real-Debrid API token")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error("Error during Real-Debrid check_link: %s", exc)
            raise ResolverError(f"Failed to check link: {exc}") from exc
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
        """Unrestrict a link using Real-Debrid /unrestrict/link."""
        if not self.is_configured:
            logger.debug("Real-Debrid resolver skipped: no API token configured")
            return None

        url = f"{self.base_url}/unrestrict/link"
        headers = self._get_headers()
        data: Dict[str, str] = {"link": link}
        if password:
            data["password"] = password

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            close_client = True

        try:
            response = await client.post(url, headers=headers, data=data)
            status = response.status_code

            # Handle auth errors
            if status in (401, 403):
                raise AuthenticationError(
                    f"Real-Debrid authentication failed ({status}): {response.text}"
                )

            # Handle rate limiting
            if status == 429:
                raise RateLimitError("Real-Debrid API rate limit reached (429)")

            # Parse JSON body to check for specific error structures
            try:
                payload = response.json()
            except Exception:
                payload = {}

            if isinstance(payload, dict) and "error" in payload:
                error_msg = str(payload.get("error", ""))
                error_code = payload.get("error_code")

                if error_code in (8, 9, 10) or "bad_token" in error_msg:
                    raise AuthenticationError(f"Real-Debrid auth error: {error_msg}")
                if error_code == 35 or "rate_limit" in error_msg:
                    raise RateLimitError(f"Real-Debrid rate limit: {error_msg}")
                if error_code in (16, 19, 20, 21) or "host_not_supported" in error_msg or "hoster_unavailable" in error_msg:
                    raise UnsupportedHosterError(f"Hoster not supported or unavailable: {error_msg}")
                if error_code == 22 or "file_not_found" in error_msg or "bad_link" in error_msg:
                    raise LinkDeadError(f"Dead link or file not found: {error_msg}")

                raise ResolverError(f"Real-Debrid error ({error_code}): {error_msg}")

            if status == 404:
                raise LinkDeadError(f"File not found on remote hoster (404): {link}")
            if status >= 400:
                raise ResolverError(f"Real-Debrid request failed with status {status}: {response.text}")

            download_url = payload.get("download", "")
            if not download_url:
                raise ResolverError("Real-Debrid response missing download URL")

            filename = payload.get("filename", "")
            filesize = int(payload.get("filesize", 0))
            hoster = payload.get("host", "")

            return ResolvedDownload(
                download_url=download_url,
                original_link=link,
                filename=filename,
                filesize=filesize,
                hoster=hoster,
                tier=self.tier_name,
                metadata=payload,
            )

        except (AuthenticationError, RateLimitError, UnsupportedHosterError, LinkDeadError, ResolverError):
            raise
        except httpx.HTTPError as exc:
            logger.error("HTTP error connecting to Real-Debrid: %s", exc)
            raise ResolverError(f"Real-Debrid network error: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()
