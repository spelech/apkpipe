"""Downloader package for streaming downloads, archive extraction, and file organization."""

from apkpipe.downloader.archive import (
    ArchiveError,
    ArchiveExtractor,
    CorruptedArchiveError,
    NoApkFoundError,
    UnsupportedArchiveError,
)
from apkpipe.downloader.engine import (
    DownloadEngine,
    DownloadError,
    DownloadHTTPError,
    DownloadProgress,
    DownloadTimeoutError,
)
from apkpipe.downloader.organizer import FileOrganizer, OrganizedFile

__all__ = [
    "DownloadEngine",
    "DownloadProgress",
    "DownloadError",
    "DownloadHTTPError",
    "DownloadTimeoutError",
    "ArchiveExtractor",
    "ArchiveError",
    "CorruptedArchiveError",
    "NoApkFoundError",
    "UnsupportedArchiveError",
    "FileOrganizer",
    "OrganizedFile",
]
