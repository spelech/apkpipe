"""Homelab integrations (Nextcloud, OCC)."""

from apkpipe.integrations.nextcloud import (
    NextcloudClient,
    NextcloudStrategy,
    OccScanResult,
    format_scan_path,
    parse_occ_output,
    trigger_occ_scan,
)

__all__ = [
    "NextcloudClient",
    "NextcloudStrategy",
    "OccScanResult",
    "format_scan_path",
    "parse_occ_output",
    "trigger_occ_scan",
]
