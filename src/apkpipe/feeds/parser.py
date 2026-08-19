"""Feed parser and candidate metadata extractor for RSS/Atom release feeds."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import email.utils
import re
from typing import Any, Dict, List, Optional
import feedparser


KNOWN_NON_RELEASER_TAGS = {
    "mod",
    "mod extra",
    "patched",
    "unlocked",
    "premium",
    "pro",
    "paid",
    "ad-free",
    "adfree",
    "ad free",
    "nightly",
    "beta",
    "final",
    "clean",
    "full",
    "lite",
    "fix",
    "multi",
    "multilingual",
    "ac3/dts",
    "ac3",
    "dts",
    "aosp",
    "no root",
    "root",
    "arm64-v8a",
    "armeabi-v7a",
    "x86",
    "x86_64",
    "universal",
    "clone",
    "plus",
    "donated",
    "vip",
    "modded",
    "cracked",
    "retail",
    "build",
    "extended",
    "standalone",
    "arm",
    "arm64",
}


@dataclass
class FeedItem:
    """Represents a single parsed RSS/Atom feed entry."""

    title: str
    link: str
    description: str = ""
    published_at: Optional[datetime] = None
    guid: Optional[str] = None
    raw_entry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateMetadata:
    """Extracted release metadata from feed item title."""

    app_name: str
    version: Optional[str] = None
    releaser: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    raw_title: str = ""


def extract_title_metadata(title: str) -> CandidateMetadata:
    """Extract app name, version, tags, and releaser from release titles."""
    if not title:
        return CandidateMetadata(app_name="", raw_title=title)

    raw_title = title.strip()

    # Extract all bracketed tags e.g. [Mod] [Balatan]
    bracket_matches = re.findall(r"\[([^\]]+)\]", raw_title)
    tags: List[str] = []
    releaser: Optional[str] = None

    if bracket_matches:
        last_bracket = bracket_matches[-1].strip()
        last_bracket_lower = last_bracket.lower()

        # If the last bracket isn't a known non-releaser tag, treat it as releaser
        if last_bracket_lower not in KNOWN_NON_RELEASER_TAGS:
            releaser = last_bracket
            tags = [b.strip() for b in bracket_matches[:-1]]
        else:
            tags = [b.strip() for b in bracket_matches]

    # Remove all bracketed chunks from the title to isolate app name and version
    cleaned = re.sub(r"\[[^\]]+\]", "", raw_title).strip()

    # Version extraction logic
    # Look for 'v' or 'V' prefix versions: e.g., v8.0.18, v0.24.1-beta0, v3-build-976-bundle
    # or numeric dotted versions without 'v': e.g., 1.18.0, 6.2.22
    version: Optional[str] = None
    app_name: str = cleaned

    v_match = re.search(r"(?:^|\s)[vV]([0-9][\w\.\-]*)(?:\s|$)", cleaned)
    if v_match:
        version = v_match.group(1)
        app_name = cleaned[: v_match.start()].strip()
    else:
        # Match dotted numeric version: e.g., 1.18.0
        dotted_match = re.search(r"(?:^|\s)([0-9]+\.[0-9]+(?:[\.\-][\w\.\-]+)*)(?:\s|$)", cleaned)
        if dotted_match:
            version = dotted_match.group(1)
            app_name = cleaned[: dotted_match.start()].strip()

    if not app_name:
        app_name = cleaned

    return CandidateMetadata(
        app_name=app_name,
        version=version,
        releaser=releaser,
        tags=tags,
        raw_title=raw_title,
    )


def parse_feed(feed_content_or_url: str) -> List[FeedItem]:
    """Parse RSS/Atom XML feed content or URL into a list of FeedItem objects."""
    if not feed_content_or_url or not feed_content_or_url.strip():
        return []

    try:
        parsed = feedparser.parse(feed_content_or_url)
    except Exception:
        return []

    if not hasattr(parsed, "entries") or not parsed.entries:
        return []

    items: List[FeedItem] = []
    for entry in parsed.entries:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()

        # Handle description / summary / content
        description = entry.get("summary") or entry.get("description") or ""
        if not description:
            content = entry.get("content")
            if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
                description = content[0].get("value", "")

        # Handle guid
        guid = entry.get("id") or entry.get("guid")

        # Handle publication date
        published_at: Optional[datetime] = None
        pub_parsed = entry.get("published_parsed")
        upd_parsed = entry.get("updated_parsed")
        pub_str = entry.get("published")
        upd_str = entry.get("updated")

        if pub_parsed:
            try:
                published_at = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_at = None
        elif upd_parsed:
            try:
                published_at = datetime(*upd_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_at = None
        elif pub_str or upd_str:
            raw_date = str(pub_str or upd_str)
            try:
                dt = email.utils.parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    published_at = dt.replace(tzinfo=timezone.utc)
                else:
                    published_at = dt.astimezone(timezone.utc)
            except Exception:
                try:
                    dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        published_at = dt.replace(tzinfo=timezone.utc)
                    else:
                        published_at = dt.astimezone(timezone.utc)
                except Exception:
                    published_at = None

        items.append(
            FeedItem(
                title=title,
                link=link,
                description=description,
                published_at=published_at,
                guid=guid,
                raw_entry=dict(entry),
            )
        )

    return items
