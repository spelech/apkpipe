"""Tiered resolution manager coordinating Real-Debrid, JDownloader 2, and Direct resolvers."""

import logging
from typing import Any, List, Optional, Sequence, Union
import urllib.parse

from apkpipe.resolvers.base import (
    BaseResolver,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    ResolverError,
    UnsupportedHosterError,
)
from apkpipe.resolvers.direct import DirectResolver
from apkpipe.resolvers.jdownloader import JDownloaderResolver
from apkpipe.resolvers.real_debrid import RealDebridResolver

logger = logging.getLogger(__name__)

# Hoster priority map (lower numbers = higher priority / better reliability)
HOSTER_PRIORITIES = {
    "mega.nz": 10,
    "mega.co.nz": 10,
    "rapidgator.net": 20,
    "rg.to": 20,
    "mediafire.com": 25,
    "dropgalaxy.in": 30,
    "dropgalaxy.com": 30,
    "dropgalaxy.co": 30,
    "1fichier.com": 35,
    "userupload.net": 40,
    "userupload.in": 40,
    "userupload.io": 40,
    "send.cm": 45,
    "sendcm.com": 45,
    "uploady.io": 50,
    "uploady.net": 50,
    "uploady.com": 50,
    "fastupload.io": 60,
    "fastupload.co": 60,
    "dailyuploads.net": 65,
    "dailyuploads.com": 65,
    "ddownload.com": 70,
    "hexupload.net": 75,
    "katfile.com": 80,
    "uploadrar.com": 85,
    "filefactory.com": 90,
    "turbobit.net": 95,
}


def _get_host_priority(link: str) -> int:
    """Return priority score for a mirror link (lower is better)."""
    try:
        parsed = urllib.parse.urlparse(link)
        host = (parsed.hostname or "").lower()
        for domain, score in HOSTER_PRIORITIES.items():
            if host == domain or host.endswith("." + domain):
                return score
    except Exception:
        pass
    return 100


class ResolutionManager:
    """Coordinates tiered link resolution across multiple mirrors and resolution tiers."""

    def __init__(
        self,
        rd_resolver: Optional[RealDebridResolver] = None,
        jd_resolver: Optional[JDownloaderResolver] = None,
        direct_resolver: Optional[DirectResolver] = None,
    ) -> None:
        """Initialize ResolutionManager with resolution tier instances."""
        self.rd_resolver = rd_resolver if rd_resolver is not None else RealDebridResolver()
        self.jd_resolver = jd_resolver if jd_resolver is not None else JDownloaderResolver()
        self.direct_resolver = direct_resolver if direct_resolver is not None else DirectResolver()

    def _sort_links_by_priority(self, links: Sequence[str]) -> List[str]:
        """Sort candidate mirror links by reliability / host priority."""
        return sorted(links, key=_get_host_priority)

    def _get_ordered_resolvers(self, preferred_tier: Optional[str] = None) -> List[BaseResolver]:
        """Return list of active resolvers in priority order."""
        resolvers: List[BaseResolver] = []
        if self.rd_resolver:
            resolvers.append(self.rd_resolver)
        if self.jd_resolver:
            resolvers.append(self.jd_resolver)
        if self.direct_resolver:
            resolvers.append(self.direct_resolver)

        if preferred_tier:
            preferred = [r for r in resolvers if getattr(r, "tier_name", "") == preferred_tier or getattr(r, "name", "") == preferred_tier]
            others = [r for r in resolvers if r not in preferred]
            resolvers = preferred + others

        return resolvers

    async def resolve(
        self,
        links: Union[str, Sequence[str]],
        package_name: Optional[str] = None,
        preferred_tier: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[ResolvedDownload]:
        """Resolve a candidate link or list of mirror links into a ResolvedDownload."""
        if isinstance(links, str):
            candidate_links = [links]
        else:
            candidate_links = list(links)

        if not candidate_links:
            return None

        sorted_links = self._sort_links_by_priority(candidate_links)
        resolvers = self._get_ordered_resolvers(preferred_tier=preferred_tier)

        for resolver in resolvers:
            tier_name = getattr(resolver, "tier_name", resolver.__class__.__name__)
            for link in sorted_links:
                try:
                    can_handle = await resolver.can_resolve(link)
                    if not can_handle:
                        continue

                    logger.debug("Attempting resolution of %s via tier '%s'", link, tier_name)
                    resolved = await resolver.resolve(
                        link=link,
                        package_name=package_name,
                        **kwargs,
                    )
                    if resolved:
                        logger.info(
                            "Successfully resolved %s via %s -> %s",
                            link,
                            tier_name,
                            resolved.download_url,
                        )
                        return resolved

                except (UnsupportedHosterError, LinkDeadError) as err:
                    logger.warning("Resolver tier '%s' failed for %s: %s", tier_name, link, err)
                    continue
                except RateLimitError as err:
                    logger.error("Rate limit encountered on tier '%s': %s", tier_name, err)
                    continue
                except ResolverError as err:
                    logger.warning("Error resolving %s with tier '%s': %s", link, tier_name, err)
                    continue
                except Exception as exc:
                    logger.exception("Unexpected error in resolver tier '%s': %s", tier_name, exc)
                    continue

        logger.warning("Failed to resolve any of candidate links: %s", candidate_links)
        return None

    async def resolve_all(
        self,
        links: Union[str, Sequence[str]],
        preferred_tier: Optional[str] = None,
        **kwargs: Any,
    ) -> List[ResolvedDownload]:
        """Attempt to resolve all provided links."""
        if isinstance(links, str):
            target_links = [links]
        else:
            target_links = list(links)

        resolved_items: List[ResolvedDownload] = []
        for link in target_links:
            res = await self.resolve(link, preferred_tier=preferred_tier, **kwargs)
            if res:
                resolved_items.append(res)
        return resolved_items

    # Alias for resolve
    resolve_links = resolve

