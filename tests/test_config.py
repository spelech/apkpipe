"""Unit tests for apkpipe configuration and settings."""

import os
from unittest.mock import patch

import pytest
from apkpipe.config import Settings, get_settings


def test_default_settings():
    """Verify that default settings have appropriate homelab values."""
    settings = Settings()
    assert settings.app_name == "APKPipe"
    assert settings.debug is False
    assert "sqlite+aiosqlite:///" in settings.database_url
    assert settings.download_dir == "/data/downloads"
    assert settings.staging_dir == "/data/staging"
    assert settings.poll_interval_seconds == 900
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.real_debrid_api_token == ""
    assert settings.jdownloader_email == ""
    assert settings.jdownloader_password == ""
    assert settings.jdownloader_device_name == ""
    assert settings.scraper_url == "http://scraper:8080"
    assert settings.nextcloud_url == ""
    assert settings.nextcloud_token == ""
    assert settings.nextcloud_occ_command == ""
    assert settings.apprise_url == ""
    assert settings.ntfy_topic == ""


def test_env_var_override():
    """Verify that environment variables override default settings."""
    env_vars = {
        "APKPIPE_APP_NAME": "CustomAPKPipe",
        "APKPIPE_DEBUG": "true",
        "APKPIPE_DATABASE_URL": "sqlite+aiosqlite:///custom_apkpipe.db",
        "APKPIPE_DOWNLOAD_DIR": "/custom/downloads",
        "APKPIPE_STAGING_DIR": "/custom/staging",
        "APKPIPE_POLL_INTERVAL_SECONDS": "300",
        "APKPIPE_HOST": "127.0.0.1",
        "APKPIPE_PORT": "8429",
        "APKPIPE_REAL_DEBRID_API_TOKEN": "rd_secret_token_123",
        "APKPIPE_JDOWNLOADER_EMAIL": "jd@example.com",
        "APKPIPE_JDOWNLOADER_PASSWORD": "secret_password",
        "APKPIPE_JDOWNLOADER_DEVICE_NAME": "MyNAS",
        "APKPIPE_SCRAPER_URL": "http://10.0.0.10:8428",
        "APKPIPE_NEXTCLOUD_URL": "https://nextcloud.example.com",
        "APKPIPE_NEXTCLOUD_TOKEN": "nc_token_xyz",
        "APKPIPE_NEXTCLOUD_OCC_COMMAND": "docker exec nc occ files:scan",
        "APKPIPE_APPRISE_URL": "http://apprise:8000/notify",
        "APKPIPE_NTFY_TOPIC": "homelab-alerts",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        settings = Settings()
        assert settings.app_name == "CustomAPKPipe"
        assert settings.debug is True
        assert settings.database_url == "sqlite+aiosqlite:///custom_apkpipe.db"
        assert settings.download_dir == "/custom/downloads"
        assert settings.staging_dir == "/custom/staging"
        assert settings.poll_interval_seconds == 300
        assert settings.host == "127.0.0.1"
        assert settings.port == 8429
        assert settings.real_debrid_api_token == "rd_secret_token_123"
        assert settings.jdownloader_email == "jd@example.com"
        assert settings.jdownloader_password == "secret_password"
        assert settings.jdownloader_device_name == "MyNAS"
        assert settings.scraper_url == "http://10.0.0.10:8428"
        assert settings.nextcloud_url == "https://nextcloud.example.com"
        assert settings.nextcloud_token == "nc_token_xyz"
        assert settings.nextcloud_occ_command == "docker exec nc occ files:scan"
        assert settings.apprise_url == "http://apprise:8000/notify"
        assert settings.ntfy_topic == "homelab-alerts"


def test_get_settings_cached():
    """Verify get_settings returns a singleton / cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
