"""Unit tests for the archive extractor module."""

import io
from pathlib import Path
import subprocess
import sys
import tarfile
from unittest.mock import MagicMock, patch
import zipfile
import pytest

from apkpipe.downloader.archive import (
    ArchiveError,
    ArchiveExtractor,
    CorruptedArchiveError,
    NoApkFoundError,
    UnsupportedArchiveError,
)


@pytest.fixture
def extractor(tmp_path: Path) -> ArchiveExtractor:
    """Fixture providing ArchiveExtractor with a custom temp directory."""
    temp_dir = tmp_path / "temp_extract"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return ArchiveExtractor(temp_dir=temp_dir)


def test_is_archive(extractor: ArchiveExtractor):
    """Test archive file detection by extension."""
    assert extractor.is_archive("test.zip") is True
    assert extractor.is_archive("test.rar") is True
    assert extractor.is_archive("test.TAR.GZ") is True
    assert extractor.is_archive("test.tgz") is True
    assert extractor.is_archive("test.7z") is True
    assert extractor.is_archive("test.apk") is False
    assert extractor.is_archive("test.txt") is False


def test_is_apk(extractor: ArchiveExtractor):
    """Test APK file detection by extension."""
    assert extractor.is_apk("app.apk") is True
    assert extractor.is_apk("app.APK") is True
    assert extractor.is_apk("app.xapk") is True
    assert extractor.is_apk("app.apks") is True
    assert extractor.is_apk("app.zip") is False
    assert extractor.is_apk("app.rar") is False


def test_extract_simple_zip(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting a standard zip archive containing an APK."""
    archive_path = tmp_path / "simple.zip"
    dest_dir = tmp_path / "extracted"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("app.apk", b"APK mock binary content")
        zf.writestr("notes.txt", b"Some release notes")

    apks = extractor.extract(archive_path, destination_dir=dest_dir)

    assert len(apks) == 1
    assert apks[0].name == "app.apk"
    assert apks[0].exists()
    assert apks[0].read_bytes() == b"APK mock binary content"
    assert apks[0].parent == dest_dir


def test_extract_nested_subfolder_flatten(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting a zip archive with nested directories and flattening."""
    archive_path = tmp_path / "nested_dirs.zip"
    dest_dir = tmp_path / "extracted_flat"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("subfolder/inner/AppName_v2.0.apk", b"Nested APK content")
        zf.writestr("subfolder/readme.txt", b"Info")

    apks = extractor.extract(archive_path, destination_dir=dest_dir, flatten=True)

    assert len(apks) == 1
    assert apks[0].name == "AppName_v2.0.apk"
    assert apks[0].parent == dest_dir
    assert apks[0].read_bytes() == b"Nested APK content"


def test_extract_nested_subfolder_preserve_structure(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting a zip archive preserving folder structure when flatten=False."""
    archive_path = tmp_path / "nested_structure.zip"
    dest_dir = tmp_path / "extracted_struct"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("deep/path/app.apk", b"Nested deep APK")

    apks = extractor.extract(archive_path, destination_dir=dest_dir, flatten=False)

    assert len(apks) == 1
    assert apks[0].exists()
    assert (dest_dir / "deep" / "path" / "app.apk").exists()


def test_extract_nested_archive_zip_in_zip(extractor: ArchiveExtractor, tmp_path: Path):
    """Test recursive extraction when an archive contains another archive."""
    inner_zip_bytes = io.BytesIO()
    with zipfile.ZipFile(inner_zip_bytes, "w") as inner_zf:
        inner_zf.writestr("final_app.apk", b"Double packed APK binary")

    outer_zip_path = tmp_path / "outer.zip"
    dest_dir = tmp_path / "extracted_nested"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(outer_zip_path, "w") as outer_zf:
        outer_zf.writestr("package.zip", inner_zip_bytes.getvalue())

    apks = extractor.extract(outer_zip_path, destination_dir=dest_dir)

    assert len(apks) == 1
    assert apks[0].name == "final_app.apk"
    assert apks[0].read_bytes() == b"Double packed APK binary"


def test_extract_nested_archive_corrupted_inner_logged(extractor: ArchiveExtractor, tmp_path: Path):
    """Test corrupted inner archive within zip is logged and skipped without breaking valid APKs."""
    outer_zip_path = tmp_path / "outer_with_bad_inner.zip"
    dest_dir = tmp_path / "extracted_bad_inner"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(outer_zip_path, "w") as outer_zf:
        outer_zf.writestr("valid_app.apk", b"Valid APK binary")
        outer_zf.writestr("corrupted_inner.zip", b"PK\x03\x04corrupted")

    apks = extractor.extract(outer_zip_path, destination_dir=dest_dir)
    assert len(apks) == 1
    assert apks[0].name == "valid_app.apk"


def test_extract_direct_apk_file(extractor: ArchiveExtractor, tmp_path: Path):
    """Test passing an uncompressed .apk file directly to extractor."""
    direct_apk = tmp_path / "direct.apk"
    direct_apk.write_bytes(b"Direct uncompressed APK")

    dest_dir = tmp_path / "extracted_direct"
    dest_dir.mkdir(parents=True, exist_ok=True)

    apks = extractor.extract(direct_apk, destination_dir=dest_dir)

    assert len(apks) == 1
    assert apks[0].name == "direct.apk"
    assert apks[0].read_bytes() == b"Direct uncompressed APK"


def test_extract_missing_source_file_raises(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting non-existent source file raises FileNotFoundError."""
    missing = tmp_path / "non_existent.zip"
    with pytest.raises(FileNotFoundError):
        extractor.extract(missing, destination_dir=tmp_path / "dest")


def test_extract_tar_archive(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting a tar.gz archive containing an APK."""
    tar_path = tmp_path / "app_archive.tar.gz"
    dest_dir = tmp_path / "extracted_tar"
    dest_dir.mkdir(parents=True, exist_ok=True)

    apk_content = b"Tar extracted APK"
    with tarfile.open(tar_path, "w:gz") as tar:
        tarinfo = tarfile.TarInfo(name="bundle/tar_app.apk")
        tarinfo.size = len(apk_content)
        tar.addfile(tarinfo, io.BytesIO(apk_content))

    apks = extractor.extract(tar_path, destination_dir=dest_dir)

    assert len(apks) == 1
    assert apks[0].name == "tar_app.apk"
    assert apks[0].read_bytes() == apk_content


def test_extract_corrupted_tar_archive(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting corrupted tar archive raises CorruptedArchiveError."""
    tar_path = tmp_path / "bad.tar.gz"
    tar_path.write_bytes(b"corrupted_tar_bytes_12345")

    with pytest.raises(CorruptedArchiveError):
        extractor.extract(tar_path, destination_dir=tmp_path / "dest")


def test_extract_rar_with_rarfile_module(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting RAR archive when rarfile library is available."""
    rar_path = tmp_path / "sample.rar"
    rar_path.write_bytes(b"Rar!\x1a\x07\x00mock")
    dest_dir = tmp_path / "extracted_rar"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Mock rarfile module
    mock_rarfile = MagicMock()
    mock_rf_instance = MagicMock()
    
    def fake_extractall(target_dir):
        (Path(target_dir) / "rar_app.apk").write_bytes(b"RAR APK content")

    mock_rf_instance.extractall.side_effect = fake_extractall
    mock_rarfile.RarFile.return_value.__enter__.return_value = mock_rf_instance

    with patch.dict(sys.modules, {"rarfile": mock_rarfile}):
        apks = extractor.extract(rar_path, destination_dir=dest_dir)
        assert len(apks) == 1
        assert apks[0].name == "rar_app.apk"
        assert apks[0].read_bytes() == b"RAR APK content"


def test_extract_rar_cli_fallback_unsupported(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting RAR archive when neither rarfile nor unrar CLI is present."""
    rar_path = tmp_path / "sample.rar"
    rar_path.write_bytes(b"Rar!\x1a\x07\x00mock")
    dest_dir = tmp_path / "dest"

    with patch.dict(sys.modules, {"rarfile": None}):
        with patch("shutil.which", return_value=None):
            with pytest.raises(UnsupportedArchiveError):
                extractor.extract(rar_path, destination_dir=dest_dir)


def test_extract_rar_cli_fallback_failure(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting RAR archive via unrar CLI when command returns non-zero error."""
    rar_path = tmp_path / "sample.rar"
    rar_path.write_bytes(b"Rar!\x1a\x07\x00mock")
    dest_dir = tmp_path / "dest_fail"

    def fake_subprocess_run(cmd, capture_output, check):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout=b"", stderr=b"CRC Error")

    with patch.dict(sys.modules, {"rarfile": None}):
        with patch("shutil.which", return_value="/usr/bin/unrar"):
            with patch("subprocess.run", side_effect=fake_subprocess_run):
                with pytest.raises(CorruptedArchiveError, match="CRC Error"):
                    extractor.extract(rar_path, destination_dir=dest_dir)


def test_extract_rar_cli_fallback_success(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting RAR archive via unrar/7z CLI subprocess."""
    rar_path = tmp_path / "sample.rar"
    rar_path.write_bytes(b"Rar!\x1a\x07\x00mock")
    dest_dir = tmp_path / "dest_rar_cli"
    dest_dir.mkdir(parents=True, exist_ok=True)

    def fake_subprocess_run(cmd, capture_output, check):
        # Extract target_dir is the last argument
        target_dir = Path(cmd[-1])
        (target_dir / "cli_app.apk").write_bytes(b"CLI APK")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    with patch.dict(sys.modules, {"rarfile": None}):
        with patch("shutil.which", return_value="/usr/bin/unrar"):
            with patch("subprocess.run", side_effect=fake_subprocess_run):
                apks = extractor.extract(rar_path, destination_dir=dest_dir)
                assert len(apks) == 1
                assert apks[0].name == "cli_app.apk"


def test_extract_7z_archive(extractor: ArchiveExtractor, tmp_path: Path):
    """Test 7z archive extraction via CLI."""
    seven_z_path = tmp_path / "sample.7z"
    seven_z_path.write_bytes(b"7z\xbc\xaf\x27\x1cmock")
    dest_dir = tmp_path / "dest_7z"
    dest_dir.mkdir(parents=True, exist_ok=True)

    def fake_subprocess_run(cmd, capture_output, check):
        for arg in cmd:
            if arg.startswith("-o"):
                target_dir = Path(arg[2:])
                (target_dir / "seven_app.apk").write_bytes(b"7z APK")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    with patch("shutil.which", return_value="/usr/bin/7z"):
        with patch("subprocess.run", side_effect=fake_subprocess_run):
            apks = extractor.extract(seven_z_path, destination_dir=dest_dir)
            assert len(apks) == 1
            assert apks[0].name == "seven_app.apk"


def test_extract_7z_archive_unsupported_when_cli_missing(extractor: ArchiveExtractor, tmp_path: Path):
    """Test 7z extraction raises UnsupportedArchiveError when 7z CLI is not available."""
    seven_z_path = tmp_path / "sample.7z"
    seven_z_path.write_bytes(b"7z\xbc\xaf\x27\x1cmock")
    dest_dir = tmp_path / "dest_no_7z"

    with patch("shutil.which", return_value=None):
        with pytest.raises(UnsupportedArchiveError):
            extractor.extract(seven_z_path, destination_dir=dest_dir)


def test_extract_7z_archive_failure_returncode(extractor: ArchiveExtractor, tmp_path: Path):
    """Test 7z extraction raises CorruptedArchiveError when CLI fails."""
    seven_z_path = tmp_path / "sample.7z"
    seven_z_path.write_bytes(b"7z\xbc\xaf\x27\x1cmock")
    dest_dir = tmp_path / "dest_7z_fail"

    def fake_subprocess_run(cmd, capture_output, check):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout=b"", stderr=b"Fatal error in 7z")

    with patch("shutil.which", return_value="/usr/bin/7z"):
        with patch("subprocess.run", side_effect=fake_subprocess_run):
            with pytest.raises(CorruptedArchiveError, match="Fatal error in 7z"):
                extractor.extract(seven_z_path, destination_dir=dest_dir)


def test_extract_unsupported_archive_format(extractor: ArchiveExtractor, tmp_path: Path):
    """Test unknown archive extension fallback raises UnsupportedArchiveError."""
    weird_path = tmp_path / "sample.customarchive"
    weird_path.write_bytes(b"Not a zip or tar binary data")
    dest_dir = tmp_path / "dest_weird"

    with pytest.raises(UnsupportedArchiveError):
        extractor.extract(weird_path, destination_dir=dest_dir)


def test_extract_overwrites_existing_destination_file(extractor: ArchiveExtractor, tmp_path: Path):
    """Test extracting overwrites any pre-existing file in destination dir."""
    archive_path = tmp_path / "overwrite.zip"
    dest_dir = tmp_path / "dest_overwrite"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_file = dest_dir / "app.apk"
    existing_file.write_bytes(b"Old APK content")

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("app.apk", b"New APK content")

    apks = extractor.extract(archive_path, destination_dir=dest_dir)
    assert len(apks) == 1
    assert apks[0].read_bytes() == b"New APK content"


def test_extract_no_apk_raises_error(extractor: ArchiveExtractor, tmp_path: Path):
    """Test that an archive without any APK files raises NoApkFoundError."""
    archive_path = tmp_path / "no_apk.zip"
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("notes.txt", b"No apk here")
        zf.writestr("image.png", b"\x89PNG")

    with pytest.raises(NoApkFoundError):
        extractor.extract(archive_path, destination_dir=dest_dir)


def test_extract_corrupted_archive_raises_error(extractor: ArchiveExtractor, tmp_path: Path):
    """Test that a corrupted archive raises CorruptedArchiveError."""
    corrupted_path = tmp_path / "corrupted.zip"
    corrupted_path.write_bytes(b"PK\x03\x04truncated_corrupted_data")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(CorruptedArchiveError):
        extractor.extract(corrupted_path, destination_dir=dest_dir)
