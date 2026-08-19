"""Tests for Watchlist Matcher and Version Comparison."""

import pytest
from apkpipe.database.models import WatchlistItem
from apkpipe.feeds.matcher import MatchResult, is_version_acceptable, match_feed_item
from apkpipe.feeds.parser import FeedItem


def test_match_result_dataclass():
    """Test MatchResult dataclass attributes and instantiation."""
    item = WatchlistItem(id=1, app_name="Nova Launcher")
    res = MatchResult(
        matched=True,
        watchlist_item=item,
        app_name="Nova Launcher",
        version="8.0.18",
        releaser="Balatan",
        reason="Matched watchlist item 'Nova Launcher'",
    )
    assert res.matched is True
    assert res.watchlist_item == item
    assert res.app_name == "Nova Launcher"
    assert res.version == "8.0.18"
    assert res.releaser == "Balatan"
    assert "Matched" in res.reason


@pytest.mark.parametrize(
    "candidate,min_version,expected",
    [
        # Min version not specified or zero
        ("1.0.0", None, True),
        ("1.0.0", "", True),
        ("1.0.0", "0.0.0", True),
        ("1.0.0", "0", True),
        (None, None, True),
        (None, "0.0.0", True),
        # Min version specified, candidate missing
        (None, "1.0.0", False),
        ("", "1.0.0", False),
        # Standard SemVer comparisons
        ("1.2.0", "1.1.0", True),
        ("1.1.0", "1.1.0", True),
        ("1.0.0", "1.1.0", False),
        ("2.0.0", "1.9.9", True),
        ("8.0.18", "8.0.0", True),
        ("8.0.18", "8.1.0", False),
        # Versions with 'v' prefix
        ("v8.0.18", "8.0.0", True),
        ("8.0.18", "v8.0.0", True),
        ("v8.0.18", "v8.1.0", False),
        # Pre-releases / calendar versioning
        ("2026.08", "2026.01", True),
        ("2025.12", "2026.01", False),
        ("1.2.3b", "1.2.0", True),
        ("0.24.1-beta0", "0.24.0", True),
        ("0.24.1-beta0", "0.25.0", False),
        ("1.0_b12", "0.9.0", True),
        ("1.0_b12", "1.0.0", False),
        # Non-standard / build-numbered versions fallback
        ("v3-build-976-bundle", "3.0.0", True),
        ("1.0_build_456", "1.0.0", True),
        ("1.0.9-final", "1.0.10", False),
        ("some-custom-tag-1.0", "some-custom-tag-0.9", True),
        ("abc", "xyz", False),
        ("xyz", "abc", True),
    ],
)
def test_is_version_acceptable(candidate, min_version, expected):
    """Test version comparison helper with standard and non-standard version strings."""
    assert is_version_acceptable(candidate, min_version) == expected


def test_match_feed_item_by_name_exact_or_substring():
    """Test matching feed items against watchlist item app_name."""
    item = FeedItem(
        title="Nova Launcher Prime v8.0.18 [Mod] [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=500001",
    )

    wl1 = WatchlistItem(id=1, app_name="Nova Launcher Prime", enabled=True, min_version="0.0.0")
    res1 = match_feed_item(item, [wl1])
    assert res1 is not None
    assert res1.matched is True
    assert res1.watchlist_item == wl1
    assert res1.version == "8.0.18"
    assert res1.releaser == "Balatan"

    # Substring / partial app name match
    wl2 = WatchlistItem(id=2, app_name="Nova Launcher", enabled=True, min_version="0.0.0")
    res2 = match_feed_item(item, [wl2])
    assert res2 is not None
    assert res2.matched is True

    # Case insensitive
    wl3 = WatchlistItem(id=3, app_name="nova launcher prime", enabled=True, min_version="0.0.0")
    res3 = match_feed_item(item, [wl3])
    assert res3 is not None
    assert res3.matched is True


def test_match_feed_item_by_regex():
    """Test matching feed items using title_regex in watchlist item."""
    item = FeedItem(
        title="Spotify: Music and Podcasts v8.9.18.520 [Premium] [derrin]",
        link="https://forum.mobilism.org/viewtopic.php?t=500002",
    )

    # Matching regex
    wl_regex = WatchlistItem(
        id=1,
        app_name="Spotify",
        title_regex=r"^Spotify.*\[Premium\]",
        enabled=True,
        min_version="0.0.0",
    )
    res = match_feed_item(item, [wl_regex])
    assert res is not None
    assert res.matched is True

    # Non-matching regex
    wl_no_match = WatchlistItem(
        id=2,
        app_name="Spotify",
        title_regex=r"^Spotify.*\[Mod Lite\]",
        enabled=True,
        min_version="0.0.0",
    )
    res_none = match_feed_item(item, [wl_no_match])
    assert res_none is None

    # Broken/invalid regex safely handled
    wl_broken = WatchlistItem(
        id=3,
        app_name="Spotify",
        title_regex=r"[unclosed-regex",
        enabled=True,
    )
    assert match_feed_item(item, [wl_broken]) is None


def test_match_feed_item_releaser_whitelist():
    """Test releaser whitelist enforcement."""
    item = FeedItem(
        title="Nova Launcher Prime v8.0.18 [Mod] [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=500001",
    )

    # Whitelist containing releaser (case-insensitive)
    wl_pass = WatchlistItem(
        id=1,
        app_name="Nova Launcher Prime",
        releaser_whitelist=["balatan", "derrin", ""],
        enabled=True,
    )
    res_pass = match_feed_item(item, [wl_pass])
    assert res_pass is not None
    assert res_pass.matched is True

    # Whitelist containing tag match
    wl_tag = WatchlistItem(
        id=2,
        app_name="Nova Launcher Prime",
        releaser_whitelist=["mod"],
        enabled=True,
    )
    assert match_feed_item(item, [wl_tag]) is not None

    # Whitelist containing bracket token in raw title
    wl_bracket = WatchlistItem(
        id=3,
        app_name="Nova Launcher Prime",
        releaser_whitelist=["Balatan"],
        enabled=True,
    )
    assert match_feed_item(item, [wl_bracket]) is not None

    # Whitelist NOT containing releaser
    wl_fail = WatchlistItem(
        id=4,
        app_name="Nova Launcher Prime",
        releaser_whitelist=["derrin", "Inotia00"],
        enabled=True,
    )
    assert match_feed_item(item, [wl_fail]) is None


def test_match_feed_item_releaser_blacklist():
    """Test releaser blacklist enforcement."""
    item = FeedItem(
        title="Nova Launcher Prime v8.0.18 [Mod] [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=500001",
    )

    # Blacklist containing candidate releaser
    wl_blacklisted = WatchlistItem(
        id=1,
        app_name="Nova Launcher Prime",
        releaser_blacklist=["Balatan", ""],
        enabled=True,
    )
    assert match_feed_item(item, [wl_blacklisted]) is None

    # Blacklist containing tag
    wl_blacklisted_tag = WatchlistItem(
        id=2,
        app_name="Nova Launcher Prime",
        releaser_blacklist=["Mod"],
        enabled=True,
    )
    assert match_feed_item(item, [wl_blacklisted_tag]) is None

    # Blacklist with other releasers
    wl_ok = WatchlistItem(
        id=3,
        app_name="Nova Launcher Prime",
        releaser_blacklist=["SpammerUser"],
        enabled=True,
    )
    res_ok = match_feed_item(item, [wl_ok])
    assert res_ok is not None
    assert res_ok.matched is True


def test_match_feed_item_min_version():
    """Test min_version gating during matching."""
    item = FeedItem(
        title="Tasker v6.2.22 [Patched]",
        link="https://forum.mobilism.org/viewtopic.php?t=500003",
    )

    # Acceptable min version
    wl_ok = WatchlistItem(id=1, app_name="Tasker", min_version="6.2.0", enabled=True)
    res_ok = match_feed_item(item, [wl_ok])
    assert res_ok is not None
    assert res_ok.matched is True

    # Higher min version (candidate rejected)
    wl_too_high = WatchlistItem(id=2, app_name="Tasker", min_version="6.3.0", enabled=True)
    assert match_feed_item(item, [wl_too_high]) is None


def test_match_feed_item_disabled_items():
    """Test that disabled watchlist items are skipped."""
    item = FeedItem(
        title="Nova Launcher Prime v8.0.18 [Mod] [Balatan]",
        link="https://forum.mobilism.org/viewtopic.php?t=500001",
    )
    wl_disabled = WatchlistItem(
        id=1,
        app_name="Nova Launcher Prime",
        enabled=False,
    )
    assert match_feed_item(item, [wl_disabled]) is None


def test_match_feed_item_multiple_candidates():
    """Test matching across a sequence of watchlist items, picking first valid match."""
    item = FeedItem(
        title="YouTube ReVanced v19.16.39 [Extended] [Inotia00]",
        link="https://forum.mobilism.org/viewtopic.php?t=500004",
    )

    wl1 = WatchlistItem(id=1, app_name="Tasker", enabled=True)
    wl2 = WatchlistItem(id=2, app_name="Spotify", enabled=True)
    wl3 = WatchlistItem(id=3, app_name="YouTube ReVanced", enabled=True, min_version="19.0.0")

    res = match_feed_item(item, [wl1, wl2, wl3])
    assert res is not None
    assert res.watchlist_item == wl3
    assert res.version == "19.16.39"
    assert res.releaser == "Inotia00"


def test_match_feed_item_no_match():
    """Test when no watchlist items match feed item."""
    item = FeedItem(
        title="Unrelated Random App v1.0 [Mod]",
        link="https://forum.mobilism.org/viewtopic.php?t=500005",
    )
    wl1 = WatchlistItem(id=1, app_name="Tasker", enabled=True)
    assert match_feed_item(item, [wl1]) is None
    assert match_feed_item(item, []) is None
