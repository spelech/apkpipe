"""Archive extraction and APK unpacking utilities supporting .zip, .rar, and .tar formats."""

import logging
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from typing import List, Optional, Union
import zipfile

logger = logging.getLogger(__name__)

# Supported archive extensions
ARCHIVE_EXTENSIONS = {
    ".zip",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".tbz2",
    ".xz",
    ".txz",
    ".7z",
}

APK_EXTENSIONS = {
    ".apk",
    ".xapk",
    ".apks",
}


class ArchiveError(Exception):
    """Base exception for archive extraction errors."""


class CorruptedArchiveError(ArchiveError):
    """Raised when an archive file is corrupt or truncated."""


class NoApkFoundError(ArchiveError):
    """Raised when an archive contains no APK or package files."""


class UnsupportedArchiveError(ArchiveError):
    """Raised when an archive format is unsupported."""


class ArchiveExtractor:
    """Extracts APK files from archives and unpacks nested structures."""

    def __init__(self, temp_dir: Optional[Union[str, Path]] = None) -> None:
        """Initialize ArchiveExtractor.

        Args:
            temp_dir: Optional base temporary directory for intermediate extraction.
        """
        self.temp_dir = Path(temp_dir) if temp_dir else None

    def is_archive(self, file_path: Union[str, Path]) -> bool:
        """Check if the given path has an archive file extension."""
        name = str(file_path).lower()
        if any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS):
            return True
        return False

    def is_apk(self, file_path: Union[str, Path]) -> bool:
        """Check if the given path is an APK, XAPK, or APKS package."""
        name = str(file_path).lower()
        return any(name.endswith(ext) for ext in APK_EXTENSIONS)

    def _extract_zip(self, archive_path: Path, target_dir: Path) -> None:
        """Extract ZIP archive."""
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    member_path = (target_dir / member.filename).resolve()
                    if not str(member_path).startswith(str(target_dir.resolve())):
                        raise CorruptedArchiveError(f"Zip slip vulnerability detected: {member.filename}")
                    zf.extract(member, target_dir)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, OSError) as exc:
            raise CorruptedArchiveError(f"Corrupted or invalid zip archive '{archive_path}': {exc}") from exc

    def _extract_tar(self, archive_path: Path, target_dir: Path) -> None:
        """Extract TAR/TGZ archive."""
        try:
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    member_path = (target_dir / member.name).resolve()
                    if not str(member_path).startswith(str(target_dir.resolve())):
                        raise CorruptedArchiveError(f"Tar slip vulnerability detected: {member.name}")
                    tf.extract(member, target_dir)
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise CorruptedArchiveError(f"Corrupted or invalid tar archive '{archive_path}': {exc}") from exc

    def _extract_rar(self, archive_path: Path, target_dir: Path) -> None:
        """Extract RAR archive using rarfile if available."""
        try:
            import rarfile  # type: ignore

            with rarfile.RarFile(archive_path, "r") as rf:
                rf.extractall(target_dir)
        except ImportError:
            # rarfile not installed, try external unrar/7z tool if available
            unrar_cmd = shutil.which("unrar") or shutil.which("7z")
            if unrar_cmd:
                import subprocess

                cmd = [unrar_cmd, "x", "-y", str(archive_path), str(target_dir)]
                res = subprocess.run(cmd, capture_output=True, check=False)
                if res.returncode != 0:
                    raise CorruptedArchiveError(f"Failed to extract RAR archive '{archive_path}': {res.stderr.decode('utf-8', errors='ignore')}")
            else:
                raise UnsupportedArchiveError("RAR extraction requires the 'rarfile' package or 'unrar'/'7z' tool.")
        except Exception as exc:
            raise CorruptedArchiveError(f"Corrupted or invalid rar archive '{archive_path}': {exc}") from exc

    def _extract_archive_file(self, archive_path: Path, target_dir: Path) -> None:
        """Dispatch archive extraction based on format."""
        name = archive_path.name.lower()
        if name.endswith(".zip"):
            self._extract_zip(archive_path, target_dir)
        elif any(name.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
            self._extract_tar(archive_path, target_dir)
        elif name.endswith(".rar"):
            self._extract_rar(archive_path, target_dir)
        elif name.endswith(".7z"):
            # Try 7z extraction
            seven_z_cmd = shutil.which("7z") or shutil.which("7za")
            if seven_z_cmd:
                import subprocess

                cmd = [seven_z_cmd, "x", "-y", f"-o{target_dir}", str(archive_path)]
                res = subprocess.run(cmd, capture_output=True, check=False)
                if res.returncode != 0:
                    raise CorruptedArchiveError(f"Failed to extract 7z archive '{archive_path}': {res.stderr.decode('utf-8', errors='ignore')}")
            else:
                raise UnsupportedArchiveError("7z extraction requires 7z CLI or library installed.")
        else:
            # Fallback attempt via zipfile or tarfile
            try:
                self._extract_zip(archive_path, target_dir)
            except Exception:
                try:
                    self._extract_tar(archive_path, target_dir)
                except Exception as exc:
                    raise UnsupportedArchiveError(f"Unknown or unsupported archive format: {archive_path}") from exc

    def _unpack_recursively(self, root_dir: Path) -> None:
        """Recursively unpack any nested archives within extracted directory."""
        found_nested = True
        extracted_archives = set()

        while found_nested:
            found_nested = False
            for current_root, _, files in os.walk(root_dir):
                for f in files:
                    file_path = Path(current_root) / f
                    if file_path in extracted_archives:
                        continue
                    if self.is_archive(file_path) and not self.is_apk(file_path):
                        nested_dest = file_path.with_suffix(".extracted")
                        nested_dest.mkdir(parents=True, exist_ok=True)
                        try:
                            self._extract_archive_file(file_path, nested_dest)
                            extracted_archives.add(file_path)
                            found_nested = True
                        except Exception as exc:
                            logger.warning("Could not extract nested archive %s: %s", file_path, exc)

    def extract(
        self,
        archive_or_apk_path: Union[str, Path],
        destination_dir: Union[str, Path],
        flatten: bool = True,
    ) -> List[Path]:
        """Extract archive or copy APK directly to destination directory.

        Args:
            archive_or_apk_path: Source archive or APK file.
            destination_dir: Destination folder where APK files will be placed.
            flatten: If True, moves APK files directly into destination root.

        Returns:
            List of Path objects for all extracted APK files.

        Raises:
            FileNotFoundError: If source path does not exist.
            CorruptedArchiveError: If archive is corrupted or unreadable.
            NoApkFoundError: If archive contains no APK files.
            UnsupportedArchiveError: If archive format cannot be handled.
        """
        source = Path(archive_or_apk_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        dest_dir = Path(destination_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Direct APK passthrough
        if self.is_apk(source) and not self.is_archive(source):
            target = dest_dir / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            return [target]

        # Extract archive in temporary working directory
        with tempfile.TemporaryDirectory(dir=self.temp_dir) as tmp_extract_dir_str:
            tmp_extract_dir = Path(tmp_extract_dir_str)
            self._extract_archive_file(source, tmp_extract_dir)
            self._unpack_recursively(tmp_extract_dir)

            # Locate all APK files in the extracted tree
            found_apks: List[Path] = []
            for root, _, files in os.walk(tmp_extract_dir):
                for f in files:
                    fp = Path(root) / f
                    if self.is_apk(fp):
                        found_apks.append(fp)

            if not found_apks:
                raise NoApkFoundError(f"No APK or package files found inside archive '{source.name}'")

            final_apks: List[Path] = []
            for apk_path in found_apks:
                if flatten:
                    target_path = dest_dir / apk_path.name
                else:
                    rel_path = apk_path.relative_to(tmp_extract_dir)
                    target_path = dest_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                if target_path.exists():
                    target_path.unlink()
                shutil.copy2(apk_path, target_path)
                final_apks.append(target_path)

            return final_apks
