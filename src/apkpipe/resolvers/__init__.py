"""Link resolution modules supporting Real-Debrid, AllDebrid, JDownloader 2, and Direct downloads."""

from apkpipe.resolvers.all_debrid import AllDebridResolver
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
    "AllDebridResolver",
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
