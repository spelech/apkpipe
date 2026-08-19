"""Direct link resolver (Tier 3) for direct downloadable URLs."""

import os
from pathlib import Path
from typing import Any, Optional
import urllib.parse

from apkpipe.resolvers.base import BaseResolver, ResolvedDownload

DIRECT_EXTENSIONS = {
    ".apk",
    ".xapk",
    ".apkm",
    ".apks",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
}


class DirectResolver(BaseResolver):
    """Tier 3 Resolver for direct file links, GitHub release assets, or scraper direct endpoints."""

    name: str = "scraper_direct"
    tier_name: str = "scraper_direct"

    async def can_resolve(self, link: str) -> bool:
        """Check if the link points to a direct downloadable asset."""
        if not link or not link.startswith(("http://", "https://")):
            return False

        try:
            parsed = urllib.parse.urlparse(link)
            path = (parsed.path or "").lower()
            if any(path.endswith(ext) for ext in DIRECT_EXTENSIONS):
                return True

            # GitHub releases download URLs
            if "github.com" in parsed.netloc and "/releases/download/" in path:
                return True

            return False
        except Exception:
            return False

    async def resolve(
        self,
        link: str,
        filename: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[ResolvedDownload]:
        """Resolve a direct link into a ResolvedDownload object."""
        if not await self.can_resolve(link):
            return None

        try:
            parsed = urllib.parse.urlparse(link)
            hoster = parsed.hostname or ""
            url_filename = Path(parsed.path).name if parsed.path else ""
        except Exception:
            hoster = ""
            url_filename = ""

        resolved_filename = filename or url_filename or "download.apk"

        return ResolvedDownload(
            download_url=link,
            original_link=link,
            filename=resolved_filename,
            filesize=0,
            hoster=hoster,
            tier=self.tier_name,
            metadata={"direct": True},
        )
