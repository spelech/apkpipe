"""Baseline scaffolding test to verify project structure, imports, and metadata."""

import importlib
import tomllib
from pathlib import Path


def test_import_apkpipe():
    """Verify that apkpipe module can be imported and has version metadata."""
    apkpipe = importlib.import_module("apkpipe")
    assert hasattr(apkpipe, "__version__")
    assert apkpipe.__version__ == "0.1.0"
    assert hasattr(apkpipe, "__app_name__")
    assert apkpipe.__app_name__ == "apkpipe"


def test_project_configuration_files_exist():
    """Verify required scaffolding files exist in the repository root."""
    root = Path(__file__).parent.parent
    
    assert (root / "pyproject.toml").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / "requirements-dev.txt").is_file()
    assert (root / "pytest.ini").is_file()
    assert (root / ".gitignore").is_file()
    assert (root / ".github" / "workflows" / "ci.yml").is_file()
    assert (root / ".github" / "workflows" / "release.yml").is_file()


def test_pyproject_metadata():
    """Verify pyproject.toml contains required project configuration."""
    root = Path(__file__).parent.parent
    pyproject_path = root / "pyproject.toml"
    assert pyproject_path.is_file()
    
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    
    assert "project" in data
    assert data["project"]["name"] == "apkpipe"
    assert data["project"]["version"] == "0.1.0"
