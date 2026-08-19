"""Unit tests for the Nextcloud file organizer and path sanitization."""

import hashlib
from pathlib import Path
from unittest.mock import patch
import pytest

from apkpipe.downloader.organizer import FileOrganizer, OrganizedFile


@pytest.fixture
def organizer(tmp_path: Path) -> FileOrganizer:
    """Fixture providing FileOrganizer instance."""
    base_dir = tmp_path / "downloads"
    base_dir.mkdir(parents=True, exist_ok=True)
    return FileOrganizer(base_download_dir=base_dir)


def test_sanitize_name(organizer: FileOrganizer):
    """Test sanitization of folder and file names."""
    # Forbidden characters: \ / : * ? " < > |
    raw = 'Nova Launcher: Prime / Edition * Pro? <v8> | "Test"'
    clean = organizer.sanitize_name(raw)
    for bad_char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        assert bad_char not in clean
    assert ".." not in clean

    # Leading / trailing dots and spaces
    assert organizer.sanitize_name("  .My App..  ") == "My App"
    # Empty string fallback
    assert organizer.sanitize_name("") == "Unknown"
    assert organizer.sanitize_name("   ") == "Unknown"
    assert organizer.sanitize_name(None) == "Unknown"


def test_format_filename(organizer: FileOrganizer):
    """Test filename formatting with various combinations of metadata."""
    # Full metadata: AppName v{Version} [{Releaser}].apk
    assert (
        organizer.format_filename(app_name="Nova Launcher", version="8.0.14", releaser="Balatan")
        == "Nova Launcher v8.0.14 [Balatan].apk"
    )

    # Version only: AppName v{Version}.apk
    assert (
        organizer.format_filename(app_name="Spotify", version="8.9.10", releaser=None)
        == "Spotify v8.9.10.apk"
    )

    # Releaser only: AppName [{Releaser}].apk
    assert (
        organizer.format_filename(app_name="Tasker", version=None, releaser="crafty")
        == "Tasker [crafty].apk"
    )

    # App name only: AppName.apk
    assert (
        organizer.format_filename(app_name="AdGuard", version=None, releaser=None)
        == "AdGuard.apk"
    )

    # Sanitization inside format_filename
    clean_name = organizer.format_filename(
        app_name="App: Pro",
        version="1.0/beta",
        releaser="mod:team",
    )
    assert ":" not in clean_name
    assert "/" not in clean_name
    assert clean_name.endswith(".apk")


def test_build_target_path(organizer: FileOrganizer, tmp_path: Path):
    """Test building complete target destination path."""
    target_path = organizer.build_target_path(
        app_name="Nova Launcher",
        version="8.0.14",
        releaser="Balatan",
        download_dir=tmp_path / "custom_downloads",
    )
    expected = tmp_path / "custom_downloads" / "Nova Launcher" / "Nova Launcher v8.0.14 [Balatan].apk"
    assert target_path == expected


def test_organizer_default_settings_fallback():
    """Test FileOrganizer base_download_dir fallback from global settings."""
    with patch("apkpipe.downloader.organizer.get_settings") as mock_settings:
        mock_settings.return_value.download_dir = "/custom/settings/dir"
        org = FileOrganizer(base_download_dir=None)
        assert org.base_download_dir == Path("/custom/settings/dir")

    with patch("apkpipe.downloader.organizer.get_settings") as mock_settings:
        mock_settings.return_value.download_dir = ""
        org_empty = FileOrganizer(base_download_dir=None)
        assert org_empty.base_download_dir == Path("/data/downloads")


def test_compute_hashes(organizer: FileOrganizer, tmp_path: Path):
    """Test computing SHA256 and MD5 hashes of a file."""
    test_file = tmp_path / "sample.apk"
    content = b"Mock APK binary content for checksum verification 12345"
    test_file.write_bytes(content)

    expected_sha256 = hashlib.sha256(content).hexdigest()
    expected_md5 = hashlib.md5(content).hexdigest()

    sha256, md5 = organizer.compute_hashes(test_file)
    assert sha256 == expected_sha256
    assert md5 == expected_md5


def test_organize_move(organizer: FileOrganizer, tmp_path: Path):
    """Test organizing a file via move operation."""
    staging_file = tmp_path / "staging" / "temp_download_123.apk"
    staging_file.parent.mkdir(parents=True, exist_ok=True)
    content = b"Binary APK data for Nova Launcher"
    staging_file.write_bytes(content)

    result = organizer.organize(
        source_file=staging_file,
        app_name="Nova Launcher",
        version="8.0.14",
        releaser="Balatan",
        move=True,
    )

    assert isinstance(result, OrganizedFile)
    assert result.app_name == "Nova Launcher"
    assert result.version == "8.0.14"
    assert result.releaser == "Balatan"
    assert result.filesize == len(content)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.md5 == hashlib.md5(content).hexdigest()
    assert result.file_path.exists()
    assert result.file_path.name == "Nova Launcher v8.0.14 [Balatan].apk"
    assert result.file_path.parent.name == "Nova Launcher"
    assert not staging_file.exists()  # Source file was moved


def test_organize_overwrites_existing_target(organizer: FileOrganizer, tmp_path: Path):
    """Test organizing overwrites existing destination file cleanly."""
    target_dir = tmp_path / "downloads" / "Nova Launcher"
    target_dir.mkdir(parents=True, exist_ok=True)
    existing_dest = target_dir / "Nova Launcher v8.0.14 [Balatan].apk"
    existing_dest.write_bytes(b"Old out-of-date APK")

    staging_file = tmp_path / "staging" / "new_download.apk"
    staging_file.parent.mkdir(parents=True, exist_ok=True)
    new_content = b"Updated fresh APK"
    staging_file.write_bytes(new_content)

    result = organizer.organize(
        source_file=staging_file,
        app_name="Nova Launcher",
        version="8.0.14",
        releaser="Balatan",
        move=True,
    )

    assert result.file_path == existing_dest
    assert result.file_path.read_bytes() == new_content


def test_organize_copy(organizer: FileOrganizer, tmp_path: Path):
    """Test organizing a file via copy operation (move=False)."""
    staging_file = tmp_path / "staging" / "copy_source.apk"
    staging_file.parent.mkdir(parents=True, exist_ok=True)
    content = b"Binary APK data for Copy Test"
    staging_file.write_bytes(content)

    result = organizer.organize(
        source_file=staging_file,
        app_name="Spotify",
        version="8.9.10",
        move=False,
    )

    assert staging_file.exists()  # Source file still exists
    assert result.file_path.exists()
    assert result.file_path.read_bytes() == content


def test_organize_missing_file_raises(organizer: FileOrganizer, tmp_path: Path):
    """Test organizing a non-existent file raises FileNotFoundError."""
    missing_file = tmp_path / "does_not_exist.apk"
    with pytest.raises(FileNotFoundError):
        organizer.organize(missing_file, app_name="MissingApp")
