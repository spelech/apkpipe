"""Tests for Feed Parser and Title Metadata Extractor."""

from datetime import datetime, timezone
from unittest.mock import patch
import pytest

from apkpipe.feeds.parser import (
    CandidateMetadata,
    FeedItem,
    extract_title_metadata,
    parse_feed,
)


SAMPLE_RSS_2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Mobilism Android Apps</title>
        <link>https://forum.mobilism.org/</link>
        <description>Android Applications Release Feed</description>
        <item>
            <title>Nova Launcher Prime v8.0.18 [Mod] [Balatan]</title>
            <link>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=500001</link>
            <description>&lt;p&gt;Delicious Nova Launcher Mod with all Prime features unlocked.&lt;/p&gt;</description>
            <pubDate>Tue, 18 Aug 2026 12:00:00 GMT</pubDate>
            <guid>https://forum.mobilism.org/viewtopic.php?t=500001</guid>
        </item>
        <item>
            <title>Spotify: Music and Podcasts v8.9.18.520 [Premium] [derrin]</title>
            <link>https://forum.mobilism.org/viewtopic.php?f=399&amp;t=500002</link>
            <description>Ad-free Spotify streaming experience.</description>
            <pubDate>Tue, 18 Aug 2026 13:30:00 +0000</pubDate>
            <guid isPermaLink="false">spotify-500002</guid>
        </item>
    </channel>
</rss>
"""

SAMPLE_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Mobilism Atom Feed</title>
    <link href="https://forum.mobilism.org/"/>
    <updated>2026-08-18T14:00:00Z</updated>
    <entry>
        <title>Tasker v6.2.22 [Patched]</title>
        <link href="https://forum.mobilism.org/viewtopic.php?t=500003"/>
        <id>urn:mobilism:topic:500003</id>
        <updated>2026-08-18T14:00:00Z</updated>
        <summary>Automation tool for Android.</summary>
    </entry>
</feed>
"""


def test_feed_item_creation():
    """Test FeedItem dataclass creation and field access."""
    now = datetime.now(timezone.utc)
    item = FeedItem(
        title="Test App v1.0 [Mod]",
        link="https://example.com/app",
        description="A great app",
        published_at=now,
        guid="guid-123",
        raw_entry={"title": "Test App v1.0 [Mod]"},
    )
    assert item.title == "Test App v1.0 [Mod]"
    assert item.link == "https://example.com/app"
    assert item.description == "A great app"
    assert item.published_at == now
    assert item.guid == "guid-123"
    assert item.raw_entry["title"] == "Test App v1.0 [Mod]"


def test_parse_feed_rss2():
    """Test parsing standard RSS 2.0 XML."""
    items = parse_feed(SAMPLE_RSS_2)
    assert len(items) == 2

    item1 = items[0]
    assert item1.title == "Nova Launcher Prime v8.0.18 [Mod] [Balatan]"
    assert item1.link == "https://forum.mobilism.org/viewtopic.php?f=399&t=500001"
    assert "Delicious Nova Launcher" in item1.description
    assert item1.guid == "https://forum.mobilism.org/viewtopic.php?t=500001"
    assert item1.published_at is not None
    assert item1.published_at.year == 2026
    assert item1.published_at.month == 8
    assert item1.published_at.day == 18
    assert item1.published_at.tzinfo == timezone.utc

    item2 = items[1]
    assert item2.title == "Spotify: Music and Podcasts v8.9.18.520 [Premium] [derrin]"
    assert item2.guid == "spotify-500002"
    assert item2.published_at is not None


def test_parse_feed_atom():
    """Test parsing Atom XML feed."""
    items = parse_feed(SAMPLE_ATOM)
    assert len(items) == 1

    item = items[0]
    assert item.title == "Tasker v6.2.22 [Patched]"
    assert item.link == "https://forum.mobilism.org/viewtopic.php?t=500003"
    assert item.guid == "urn:mobilism:topic:500003"
    assert "Automation tool" in item.description
    assert item.published_at is not None
    assert item.published_at.year == 2026


def test_parse_feed_empty_or_corrupt():
    """Test parse_feed handles empty or corrupted feed contents safely."""
    assert parse_feed("") == []
    assert parse_feed("   ") == []
    assert parse_feed("Not valid XML <><> <<<<<") == []


def test_parse_feed_missing_fields():
    """Test parse_feed gracefully handles entries with missing optional fields."""
    partial_rss = """<?xml version="1.0"?>
    <rss version="2.0">
        <channel>
            <item>
                <title>Bare Minimum Item</title>
            </item>
        </channel>
    </rss>
    """
    items = parse_feed(partial_rss)
    assert len(items) == 1
    assert items[0].title == "Bare Minimum Item"
    assert items[0].link == ""
    assert items[0].description == ""
    assert items[0].published_at is None
    assert items[0].guid is None


def test_parse_feed_description_fallback():
    """Test parse_feed fallback when description field is present instead of summary."""
    mock_entry = {
        "title": "Desc Item",
        "description": "Found in description field",
    }
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value.entries = [mock_entry]
        items = parse_feed("<dummy></dummy>")
        assert len(items) == 1
        assert items[0].description == "Found in description field"


def test_parse_feed_content_and_dates():
    """Test various date formats and content fields in feed entries."""
    xml_with_content = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <title>Test Content Feed</title>
        <entry>
            <title>App Content Item</title>
            <content type="html">&lt;p&gt;Detailed content body&lt;/p&gt;</content>
            <updated>2026-08-18T15:30:00Z</updated>
        </entry>
    </feed>
    """
    items = parse_feed(xml_with_content)
    assert len(items) == 1
    assert "Detailed content body" in items[0].description
    assert items[0].published_at is not None
    assert items[0].published_at.hour == 15

    # Feed with ISO date string fallback
    mock_entry = {
        "title": "Fallback Date Item",
        "published": "2026-08-18T10:00:00Z",
    }
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value.entries = [mock_entry]
        items = parse_feed("<dummy></dummy>")
        assert len(items) == 1
        assert items[0].published_at is not None
        assert items[0].published_at.year == 2026

    # Feed with invalid date string
    mock_entry_bad_date = {
        "title": "Bad Date Item",
        "published": "not-a-real-date",
    }
    with patch("feedparser.parse") as mock_parse:
        mock_parse.return_value.entries = [mock_entry_bad_date]
        items = parse_feed("<dummy></dummy>")
        assert len(items) == 1
        assert items[0].published_at is None

    # Exception during feedparser.parse
    with patch("feedparser.parse", side_effect=RuntimeError("Boom")):
        assert parse_feed("<xml>crash</xml>") == []


@pytest.mark.parametrize(
    "title,expected_app,expected_version,expected_releaser,expected_tags",
    [
        (
            "Nova Launcher Prime v8.0.18 [Mod] [Balatan]",
            "Nova Launcher Prime",
            "8.0.18",
            "Balatan",
            ["Mod"],
        ),
        (
            "Spotify: Music and Podcasts v8.9.18.520 [Premium] [derrin]",
            "Spotify: Music and Podcasts",
            "8.9.18.520",
            "derrin",
            ["Premium"],
        ),
        (
            "Tasker v6.2.22 [Patched]",
            "Tasker",
            "6.2.22",
            None,
            ["Patched"],
        ),
        (
            "MX Player Pro v1.74.4 [AC3/DTS] [Patched] [Mod] [OsitKP]",
            "MX Player Pro",
            "1.74.4",
            "OsitKP",
            ["AC3/DTS", "Patched", "Mod"],
        ),
        (
            "SD Maid 2/SE - System Cleaner v0.24.1-beta0 [Unlocked]",
            "SD Maid 2/SE - System Cleaner",
            "0.24.1-beta0",
            None,
            ["Unlocked"],
        ),
        (
            "YouTube ReVanced v19.16.39 [Extended] [Inotia00]",
            "YouTube ReVanced",
            "19.16.39",
            "Inotia00",
            ["Extended"],
        ),
        (
            "AdGuard - Block Ads Without Root v4.3.49 [Nightly] [Premium] [Balatan]",
            "AdGuard - Block Ads Without Root",
            "4.3.49",
            "Balatan",
            ["Nightly", "Premium"],
        ),
        (
            "RetroArch 1.18.0 [Clean]",
            "RetroArch",
            "1.18.0",
            None,
            ["Clean"],
        ),
        (
            "Moon+ Reader Pro [Paid]",
            "Moon+ Reader Pro",
            None,
            None,
            ["Paid"],
        ),
        (
            "Poweramp Music Player (arm64-v8a) v3-build-976-bundle [Full] [timozas]",
            "Poweramp Music Player (arm64-v8a)",
            "3-build-976-bundle",
            "timozas",
            ["Full"],
        ),
        (
            "Simple App Without Brackets",
            "Simple App Without Brackets",
            None,
            None,
            [],
        ),
    ],
)
def test_extract_title_metadata(
    title, expected_app, expected_version, expected_releaser, expected_tags
):
    """Test metadata extraction from various Mobilism release title formats."""
    meta = extract_title_metadata(title)
    assert isinstance(meta, CandidateMetadata)
    assert meta.app_name == expected_app
    assert meta.version == expected_version
    assert meta.releaser == expected_releaser
    assert meta.tags == expected_tags
    assert meta.raw_title == title


def test_extract_title_metadata_empty():
    """Test extract_title_metadata with empty or None input."""
    meta = extract_title_metadata("")
    assert meta.app_name == ""
    assert meta.raw_title == ""
