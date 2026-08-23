"""Application configuration and environment settings using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings supporting environment variable overrides."""

    app_name: str = "APKPipe"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///apkpipe.db"
    download_dir: str = "/data/downloads"
    staging_dir: str = "/data/staging"
    poll_interval_seconds: int = 900
    host: str = "0.0.0.0"
    port: int = 8000

    # Downloader / Resolver settings
    real_debrid_api_token: str = ""
    alldebrid_api_key: Optional[str] = Field(
        default=None, validation_alias="APKPIPE_ALLDEBRID_API_KEY"
    )
    alldebrid_agent: str = Field(
        default="apkpipe", validation_alias="APKPIPE_ALLDEBRID_AGENT"
    )
    jdownloader_email: str = ""
    jdownloader_password: str = ""
    jdownloader_device_name: str = ""
    jdownloader_watch_dir: str = ""
    scraper_url: str = "http://scraper:8080"

    # Integration settings
    nextcloud_url: str = ""
    nextcloud_token: str = ""
    nextcloud_occ_command: str = ""
    apprise_url: str = ""
    ntfy_topic: str = ""

    model_config = SettingsConfigDict(
        env_prefix="APKPIPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
