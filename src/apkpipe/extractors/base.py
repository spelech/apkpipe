"""Base interfaces and data structures for download link extractors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import httpx


@dataclass
class ExtractedLink:
    """Represents a download mirror link extracted from a release post or topic."""

    url: str
    hoster: str
    raw_text: Optional[str] = None
    priority: int = 100


class BaseExtractor(ABC):
    """Abstract base class for topic/post mirror link extractors."""

    @abstractmethod
    async def extract_from_html(self, html_content: str) -> List[ExtractedLink]:
        """Extract download mirror links from HTML content."""
        pass

    @abstractmethod
    async def fetch_and_extract(
        self,
        topic_url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[ExtractedLink]:
        """Fetch topic page at topic_url and extract download mirror links."""
        pass
