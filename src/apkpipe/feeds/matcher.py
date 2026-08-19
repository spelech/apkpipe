"""Watchlist matching and SemVer version gating engine."""

from dataclasses import dataclass
import re
from typing import Optional, Sequence
from packaging.version import InvalidVersion, Version

from apkpipe.database.models import WatchlistItem
from apkpipe.feeds.parser import FeedItem, extract_title_metadata


@dataclass
class MatchResult:
    """Represents the matching result between a FeedItem and a WatchlistItem."""

    matched: bool
    watchlist_item: Optional[WatchlistItem] = None
    app_name: str = ""
    version: Optional[str] = None
    releaser: Optional[str] = None
    reason: str = ""


def _normalize_version_string(v_str: str) -> str:
    """Strip leading 'v', 'V' and whitespace from version string."""
    clean = v_str.strip()
    if clean.lower().startswith("v"):
        clean = clean[1:].lstrip()
    return clean


def is_version_acceptable(candidate_version: Optional[str], min_version: Optional[str]) -> bool:
    """Check if candidate version satisfies min_version requirement.

    Handles standard SemVer as well as build strings, beta tags, and calendar versioning.
    """
    if min_version is None or min_version.strip() in ("", "0", "0.0", "0.0.0", "0.0.0.0"):
        return True

    if candidate_version is None or not candidate_version.strip():
        return False

    c_norm = _normalize_version_string(candidate_version)
    m_norm = _normalize_version_string(min_version)

    # 1. Try direct packaging.version.Version
    try:
        c_ver = Version(c_norm)
        m_ver = Version(m_norm)
        return c_ver >= m_ver
    except InvalidVersion:
        pass

    # 2. Try handling build identifiers (e.g., _b12, -build-976) as local versions (+)
    try:
        c_build = re.sub(r"[_\-](build[_\-]*)?(\d+.*)$", r"+\2", c_norm, flags=re.IGNORECASE)
        m_build = re.sub(r"[_\-](build[_\-]*)?(\d+.*)$", r"+\2", m_norm, flags=re.IGNORECASE)
        c_ver = Version(c_build)
        m_ver = Version(m_build)
        return c_ver >= m_ver
    except InvalidVersion:
        pass

    # 3. Numeric tuple fallback
    c_nums = [int(x) for x in re.findall(r"\d+", c_norm)]
    m_nums = [int(x) for x in re.findall(r"\d+", m_norm)]

    if c_nums and m_nums:
        max_len = max(len(c_nums), len(m_nums))
        c_pad = tuple(c_nums + [0] * (max_len - len(c_nums)))
        m_pad = tuple(m_nums + [0] * (max_len - len(m_nums)))
        return c_pad >= m_pad

    # 4. Lexicographical fallback
    return c_norm >= m_norm


def match_feed_item(
    item: FeedItem,
    watchlist_items: Sequence[WatchlistItem],
) -> Optional[MatchResult]:
    """Evaluate a FeedItem against a sequence of WatchlistItem records.

    Checks title / regex matching, releaser whitelist/blacklist, and min_version gating.
    Returns MatchResult for the first matching watchlist item, or None.
    """
    meta = extract_title_metadata(item.title)

    for wl in watchlist_items:
        if not getattr(wl, "enabled", True):
            continue

        # 1. Title / Regex matching
        title_matched = False
        title_regex = getattr(wl, "title_regex", None)
        app_name = getattr(wl, "app_name", "")

        if title_regex and title_regex.strip():
            try:
                if re.search(title_regex.strip(), item.title, re.IGNORECASE) or re.search(
                    title_regex.strip(), meta.app_name, re.IGNORECASE
                ):
                    title_matched = True
            except re.error:
                title_matched = False
        elif app_name and app_name.strip():
            target_name = app_name.strip().lower()
            if target_name in item.title.lower() or target_name in meta.app_name.lower():
                title_matched = True

        if not title_matched:
            continue

        # 2. Releaser Whitelist & Blacklist evaluation
        cand_releaser = meta.releaser
        releaser_blacklist = getattr(wl, "releaser_blacklist", []) or []
        releaser_whitelist = getattr(wl, "releaser_whitelist", []) or []

        if releaser_blacklist:
            blacklisted = False
            for b in releaser_blacklist:
                b_clean = b.strip().lower() if isinstance(b, str) else ""
                if not b_clean:
                    continue
                if cand_releaser and cand_releaser.strip().lower() == b_clean:
                    blacklisted = True
                    break
                if any(t.strip().lower() == b_clean for t in meta.tags):
                    blacklisted = True
                    break
                if f"[{b_clean}]" in item.title.lower():
                    blacklisted = True
                    break
            if blacklisted:
                continue

        if releaser_whitelist:
            whitelisted = False
            for w in releaser_whitelist:
                w_clean = w.strip().lower() if isinstance(w, str) else ""
                if not w_clean:
                    continue
                if cand_releaser and cand_releaser.strip().lower() == w_clean:
                    whitelisted = True
                    break
                if any(t.strip().lower() == w_clean for t in meta.tags):
                    whitelisted = True
                    break
                if f"[{w_clean}]" in item.title.lower():
                    whitelisted = True
                    break
            if not whitelisted:
                continue

        # 3. Version gating
        min_version = getattr(wl, "min_version", None)
        if not is_version_acceptable(meta.version, min_version):
            continue

        # Matched successfully
        return MatchResult(
            matched=True,
            watchlist_item=wl,
            app_name=meta.app_name or app_name,
            version=meta.version,
            releaser=meta.releaser,
            reason=f"Matched watchlist item '{app_name}' (id={getattr(wl, 'id', None)})",
        )

    return None
