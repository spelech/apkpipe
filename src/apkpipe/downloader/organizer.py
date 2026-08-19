"""Nextcloud file organizer, filesystem path sanitization, and checksum verification."""

from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
import re
import shutil
from typing import Optional, Tuple, Union

from apkpipe.config import get_settings

logger = logging.getLogger(__name__)

# Disallowed characters in filesystem paths and Nextcloud sync
INVALID_CHARS_RE = re.compile(r'[\\/:*?"<>|\0\r\n\t]+')
MULTIPLE_SPACES_RE = re.compile(r'\s+')
MULTIPLE_HYPHENS_RE = re.compile(r'-{2,}')


@dataclass
class OrganizedFile:
    """Represents a finalized, organized file with verified checksums and placement."""

    file_path: Path
    app_name: str
    version: Optional[str] = None
    releaser: Optional[str] = None
    sha256: str = ""
    md5: str = ""
    filesize: int = 0
    destination_path: Path = field(default_factory=Path)


class FileOrganizer:
    """Organizes downloaded APKs into Nextcloud-compatible folder structures."""

    def __init__(self, base_download_dir: Optional[Union[str, Path]] = None) -> None:
        """Initialize FileOrganizer.

        Args:
            base_download_dir: Root directory for structured downloads (e.g. /data/downloads).
        """
        if base_download_dir is not None:
            self.base_download_dir = Path(base_download_dir)
        else:
            settings_dir = get_settings().download_dir
            self.base_download_dir = Path(settings_dir) if settings_dir else Path("/data/downloads")

    def sanitize_name(self, name: Optional[str], fallback: str = "Unknown") -> str:
        """Sanitize a file or directory name for filesystem and Nextcloud compatibility.

        Replaces forbidden characters (/ \\ : * ? " < > |) with safe alternatives,
        removes control characters, trims whitespace and trailing dots, and avoids path traversal.

        Args:
            name: Raw input string.
            fallback: Default string to use if sanitized result is empty.

        Returns:
            Sanitized safe string.
        """
        if not name:
            return fallback

        # Replace colon, slash, backslash with hyphen, and remove other invalid chars
        cleaned = re.sub(r'[:/\\]+', '-', str(name))
        cleaned = INVALID_CHARS_RE.sub('', cleaned)

        # Remove path traversal
        cleaned = cleaned.replace('..', '')

        # Normalize whitespace and hyphens
        cleaned = MULTIPLE_SPACES_RE.sub(' ', cleaned)
        cleaned = MULTIPLE_HYPHENS_RE.sub('-', cleaned)

        # Strip surrounding whitespace, hyphens, and dots
        cleaned = cleaned.strip(" .-_")

        return cleaned if cleaned else fallback

    def format_filename(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        extension: str = ".apk",
    ) -> str:
        """Format standard APK filename: '{AppName} v{Version} [{Releaser}].apk'.

        Args:
            app_name: Application name.
            version: Optional version tag.
            releaser: Optional releaser or team name.
            extension: File extension including dot (default: .apk).

        Returns:
            Formatted and sanitized filename.
        """
        clean_app = self.sanitize_name(app_name, fallback="App")
        clean_version = self.sanitize_name(version, fallback="") if version else ""
        clean_releaser = self.sanitize_name(releaser, fallback="") if releaser else ""

        # Normalize leading 'v' in version if present
        if clean_version:
            clean_version = re.sub(r'^[vV]+', '', clean_version).strip()

        parts = [clean_app]
        if clean_version:
            parts.append(f"v{clean_version}")
        if clean_releaser:
            parts.append(f"[{clean_releaser}]")

        ext = extension if extension.startswith(".") else f".{extension}"
        formatted = " ".join(parts) + ext
        return formatted

    def build_target_path(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        download_dir: Optional[Union[str, Path]] = None,
        extension: str = ".apk",
    ) -> Path:
        """Build full target destination path: '{base_dir}/{AppName}/{Filename}'.

        Args:
            app_name: Application name.
            version: Optional version.
            releaser: Optional releaser.
            download_dir: Optional override for base download directory.
            extension: File extension.

        Returns:
            Resolved Path object for the target file.
        """
        base = Path(download_dir) if download_dir is not None else self.base_download_dir
        folder_name = self.sanitize_name(app_name, fallback="App")
        filename = self.format_filename(app_name, version=version, releaser=releaser, extension=extension)
        return base / folder_name / filename

    def compute_hashes(
        self,
        file_path: Union[str, Path],
        chunk_size: int = 65536,
    ) -> Tuple[str, str]:
        """Compute SHA256 and MD5 hashes of a file.

        Args:
            file_path: Path to target file.
            chunk_size: Read buffer size in bytes.

        Returns:
            Tuple of (sha256_hex, md5_hex).
        """
        sha256 = hashlib.sha256()
        md5 = hashlib.md5()

        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
                md5.update(chunk)

        return sha256.hexdigest(), md5.hexdigest()

    def organize(
        self,
        source_file: Union[str, Path],
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        download_dir: Optional[Union[str, Path]] = None,
        move: bool = True,
    ) -> OrganizedFile:
        """Move or copy downloaded APK to standard target folder and compute checksums.

        Args:
            source_file: Path to downloaded APK file.
            app_name: Application name.
            version: Optional version string.
            releaser: Optional releaser name.
            download_dir: Optional destination root override.
            move: If True, moves the source file; if False, copies it.

        Returns:
            OrganizedFile containing file paths and metadata.

        Raises:
            FileNotFoundError: If source_file does not exist.
        """
        src = Path(source_file)
        if not src.exists():
            raise FileNotFoundError(f"Source file does not exist: {src}")

        ext = src.suffix if src.suffix else ".apk"
        target_path = self.build_target_path(
            app_name=app_name,
            version=version,
            releaser=releaser,
            download_dir=download_dir,
            extension=ext,
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists() and src.resolve() != target_path.resolve():
            target_path.unlink()

        if move:
            shutil.move(str(src), str(target_path))
        else:
            shutil.copy2(src, target_path)

        sha256, md5 = self.compute_hashes(target_path)
        filesize = target_path.stat().st_size

        logger.info(
            "Organized %s -> %s (Size: %d bytes, SHA256: %s)",
            src.name,
            target_path,
            filesize,
            sha256,
        )

        return OrganizedFile(
            file_path=target_path,
            app_name=app_name,
            version=version,
            releaser=releaser,
            sha256=sha256,
            md5=md5,
            filesize=filesize,
            destination_path=target_path,
        )
