"""Base classes, dataclasses, and exceptions for link resolvers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ResolvedDownload:
    """Represents a successfully resolved download item ready for streaming or capture."""

    download_url: str
    original_link: str
    filename: str = ""
    filesize: int = 0
    hoster: str = ""
    tier: str = "direct"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResolverError(Exception):
    """Base exception for all resolver-related errors."""


class UnsupportedHosterError(ResolverError):
    """Raised when the target hoster is not supported by the resolver."""


class LinkDeadError(ResolverError):
    """Raised when the remote file has been deleted or link is invalid."""


class RateLimitError(ResolverError):
    """Raised when the resolver API rate limit has been exceeded."""


class AuthenticationError(ResolverError):
    """Raised when resolver authentication fails or token is expired."""


class BaseResolver(ABC):
    """Abstract base class for download link resolvers."""

    name: str = "base"
    tier_name: str = "base"

    @abstractmethod
    async def can_resolve(self, link: str) -> bool:
        """Check if this resolver can potentially resolve the given link."""
        raise NotImplementedError

    @abstractmethod
    async def resolve(self, link: str, **kwargs: Any) -> Optional[ResolvedDownload]:
        """Resolve a mirror or download link into a direct download target."""
        raise NotImplementedError
