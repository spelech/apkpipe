"""Feeds module for APKPipe RSS parsing and watchlist matching."""

from apkpipe.feeds.matcher import (
    MatchResult,
    is_version_acceptable,
    match_feed_item,
)
from apkpipe.feeds.parser import (
    CandidateMetadata,
    FeedItem,
    extract_title_metadata,
    parse_feed,
)

__all__ = [
    "FeedItem",
    "CandidateMetadata",
    "extract_title_metadata",
    "parse_feed",
    "MatchResult",
    "is_version_acceptable",
    "match_feed_item",
]
