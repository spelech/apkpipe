"""Mobilism topic scraper and mirror link extractor."""

import html
import re
from typing import Dict, List, Optional, Set
import urllib.parse
from bs4 import BeautifulSoup
import httpx

from apkpipe.extractors.base import BaseExtractor, ExtractedLink
from apkpipe.extractors.scraper_client import PlaywrightScraperClient


KNOWN_HOSTERS: Dict[str, List[str]] = {
    "mega": ["mega.nz", "mega.co.nz"],
    "rapidgator": ["rapidgator.net", "rg.to"],
    "mediafire": ["mediafire.com"],
    "dropgalaxy": ["dropgalaxy.in", "dropgalaxy.com", "dropgalaxy.co"],
    "1fichier": ["1fichier.com"],
    "userupload": ["userupload.net", "userupload.in", "userupload.io"],
    "sendcm": ["send.cm", "sendcm.com"],
    "uploady": ["uploady.io", "uploady.net", "uploady.com"],
    "fastupload": ["fastupload.io", "fastupload.co"],
    "dailyuploads": ["dailyuploads.net", "dailyuploads.com"],
    "ddownload": ["ddownload.com"],
    "hexupload": ["hexupload.net"],
    "katfile": ["katfile.com"],
    "uploadrar": ["uploadrar.com"],
    "filefactory": ["filefactory.com"],
    "turbobit": ["turbobit.net"],
    "zippyshare": ["zippyshare.com"],
}

DEFAULT_PRIORITIES: Dict[str, int] = {
    "mega": 10,
    "rapidgator": 20,
    "mediafire": 25,
    "dropgalaxy": 30,
    "1fichier": 35,
    "userupload": 40,
    "sendcm": 45,
    "uploady": 50,
    "fastupload": 60,
    "dailyuploads": 65,
    "ddownload": 70,
    "hexupload": 75,
    "katfile": 80,
    "uploadrar": 85,
    "filefactory": 90,
    "turbobit": 95,
    "generic": 100,
}

IGNORED_DOMAINS: Set[str] = {
    "mobilism.org",
    "mobilism.me",
    "forum.mobilism.org",
    "google.com",
    "play.google.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "facebook.com",
    "postimg.cc",
    "imgur.com",
    "imagebam.com",
    "ibb.co",
    "t.me",
    "telegram.org",
    "virustotal.com",
    "github.com",
}

CLOUDFLARE_SIGNATURES: List[str] = [
    "just a moment...",
    "cf-browser-verification",
    "attention required! | cloudflare",
    "ray id:",
    "cloudflare-static",
]


def identify_hoster(url: str) -> str:
    """Identify the file hoster service name from a URL."""
    if not url:
        return "generic"
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
    except Exception:
        return "generic"

    for hoster_name, domains in KNOWN_HOSTERS.items():
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return hoster_name
    return "generic"


def clean_and_unwrap_url(url: str) -> str:
    """Strip redirect wrappers (anonym.to, ouo.io, etc.) and clean tracking characters."""
    if not url:
        return ""

    url = html.unescape(url).strip()
    url = re.sub(r'[\'",<>\),]+$', "", url).strip()

    # Unwrap known redirect services
    redirector_patterns = [
        r"^https?://(?:www\.)?anonym\.(?:to|click)/\?(https?://.+)$",
        r"^https?://(?:www\.)?href\.li/\?(https?://.+)$",
        r"^https?://(?:www\.)?dereferer\.me/\?(https?://.+)$",
        r"^https?://(?:www\.)?nullrefer\.com/\?(https?://.+)$",
        r"^https?://(?:www\.)?safelinking\.net/p/[^?]+\?(https?://.+)$",
        r"^https?://(?:www\.)?ouo\.(?:io|press)/[^\?]*\?s=(https?://.+)$",
    ]

    for pattern in redirector_patterns:
        match = re.match(pattern, url, re.IGNORECASE)
        if match:
            inner_url = match.group(1)
            return clean_and_unwrap_url(inner_url)

    # Check query params for destination URLs
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.query:
            query_params = urllib.parse.parse_qs(parsed.query)
            for key in ["url", "dest", "target", "link", "s"]:
                if key in query_params:
                    val = query_params[key][0]
                    if val.startswith("http://") or val.startswith("https://"):
                        return clean_and_unwrap_url(val)
    except Exception:
        pass

    return url


def is_ignored_url(url: str) -> bool:
    """Check if the given URL belongs to an ignored domain or invalid scheme."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        host = (parsed.hostname or "").lower()
        for ignored in IGNORED_DOMAINS:
            if host == ignored or host.endswith("." + ignored):
                return True
        return False
    except Exception:
        return True


class MobilismExtractor(BaseExtractor):
    """Extractor for Mobilism forum topics and release posts."""

    def __init__(
        self,
        scraper_client: Optional[PlaywrightScraperClient] = None,
        hoster_priorities: Optional[Dict[str, int]] = None,
    ) -> None:
        self.scraper_client = scraper_client
        self.hoster_priorities = hoster_priorities or DEFAULT_PRIORITIES

    def _get_priority(self, hoster: str) -> int:
        return self.hoster_priorities.get(hoster, self.hoster_priorities.get("generic", 100))

    async def extract_from_html(self, html_content: str) -> List[ExtractedLink]:
        """Extract download mirror links from HTML post content."""
        if not html_content or not isinstance(html_content, str):
            return []

        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception:
            return []

        # Focus on post content container if available, otherwise search whole document
        content_container = soup.find("div", class_="postbody") or soup.find("div", class_="content") or soup

        raw_candidates: List[tuple[str, Optional[str]]] = []

        # 1. Extract from anchor tags
        for a_tag in content_container.find_all("a", href=True):
            raw_href = str(a_tag["href"]).strip()
            anchor_text = a_tag.get_text(strip=True) or None
            cleaned = clean_and_unwrap_url(raw_href)
            if cleaned and not is_ignored_url(cleaned):
                raw_candidates.append((cleaned, anchor_text))

        # 2. Extract plain text URLs
        text_content = content_container.get_text(separator=" ")
        url_regex = re.compile(r"https?://[^\s<>\"\'\)\]]+", re.IGNORECASE)
        for match in url_regex.finditer(text_content):
            raw_url = match.group(0)
            cleaned = clean_and_unwrap_url(raw_url)
            if cleaned and not is_ignored_url(cleaned):
                raw_candidates.append((cleaned, None))

        # Deduplicate while preserving order and best metadata
        seen_urls: Set[str] = set()
        extracted: List[ExtractedLink] = []

        for url, raw_text in raw_candidates:
            normalized_url = url.rstrip("/")
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)

            hoster = identify_hoster(url)
            priority = self._get_priority(hoster)
            extracted.append(
                ExtractedLink(
                    url=url,
                    hoster=hoster,
                    raw_text=raw_text,
                    priority=priority,
                )
            )

        # Sort extracted links by priority (lowest integer value = highest priority)
        extracted.sort(key=lambda item: item.priority)
        return extracted

    async def fetch_and_extract(
        self,
        topic_url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[ExtractedLink]:
        """Fetch topic page at topic_url and extract download mirror links."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    )
                },
                follow_redirects=True,
                timeout=30.0,
            )
            should_close = True

        try:
            resp = await client.get(topic_url)
            body_text = resp.text or ""
            body_lower = body_text.lower()

            is_cf_challenge = resp.status_code in (403, 503) or any(
                sig in body_lower for sig in CLOUDFLARE_SIGNATURES
            )

            if is_cf_challenge and self.scraper_client:
                rendered_html = await self.scraper_client.render_page(topic_url, client=client)
                return await self.extract_from_html(rendered_html)

            resp.raise_for_status()
            return await self.extract_from_html(body_text)

        finally:
            if should_close:
                await client.aclose()
