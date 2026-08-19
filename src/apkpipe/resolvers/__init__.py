"""Link resolution modules supporting Real-Debrid, JDownloader 2, and Direct downloads."""

from apkpipe.resolvers.base import (
    AuthenticationError,
    BaseResolver,
    LinkDeadError,
    RateLimitError,
    ResolvedDownload,
    ResolverError,
    UnsupportedHosterError,
)
from apkpipe.resolvers.direct import DirectResolver
from apkpipe.resolvers.jdownloader import JDownloaderResolver
from apkpipe.resolvers.manager import ResolutionManager, ResolverManager
from apkpipe.resolvers.real_debrid import RealDebridResolver

__all__ = [
    "AuthenticationError",
    "BaseResolver",
    "DirectResolver",
    "JDownloaderResolver",
    "LinkDeadError",
    "RateLimitError",
    "ResolutionManager",
    "ResolverManager",
    "ResolvedDownload",
    "ResolverError",
    "RealDebridResolver",
    "UnsupportedHosterError",
]
