"""Unit tests for Mobilism mirror link extractor."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from apkpipe.extractors.base import BaseExtractor, ExtractedLink
from apkpipe.extractors.mobilism import (
    MobilismExtractor,
    clean_and_unwrap_url,
    identify_hoster,
    is_ignored_url,
)
from apkpipe.extractors.scraper_client import PlaywrightScraperClient


class DummyExtractor(BaseExtractor):
    """Dummy extractor to verify abstract BaseExtractor interface."""

    async def extract_from_html(self, html_content: str):
        return []

    async def fetch_and_extract(self, topic_url: str, client=None):
        return []


def test_extracted_link_dataclass():
    """Test ExtractedLink dataclass properties and defaults."""
    link = ExtractedLink(
        url="https://rapidgator.net/file/12345/app.apk.html",
        hoster="rapidgator",
    )
    assert link.url == "https://rapidgator.net/file/12345/app.apk.html"
    assert link.hoster == "rapidgator"
    assert link.raw_text is None
    assert link.priority == 100

    link_custom = ExtractedLink(
        url="https://mega.nz/file/abc#123",
        hoster="mega",
        raw_text="Mirror 1",
        priority=10,
    )
    assert link_custom.raw_text == "Mirror 1"
    assert link_custom.priority == 10


def test_identify_hoster():
    """Test host recognition across known file hosters."""
    assert identify_hoster("https://rapidgator.net/file/12345/app.apk.html") == "rapidgator"
    assert identify_hoster("http://rg.to/file/abc/app.apk") == "rapidgator"
    assert identify_hoster("https://uploady.io/abc123") == "uploady"
    assert identify_hoster("https://uploady.net/xyz") == "uploady"
    assert identify_hoster("https://uploady.com/xyz") == "uploady"
    assert identify_hoster("https://dropgalaxy.in/abc123") == "dropgalaxy"
    assert identify_hoster("https://dropgalaxy.com/xyz") == "dropgalaxy"
    assert identify_hoster("https://dropgalaxy.co/xyz") == "dropgalaxy"
    assert identify_hoster("https://mega.nz/file/abc#123") == "mega"
    assert identify_hoster("https://mega.co.nz/#!xyz") == "mega"
    assert identify_hoster("https://userupload.net/abc") == "userupload"
    assert identify_hoster("https://userupload.in/xyz") == "userupload"
    assert identify_hoster("https://userupload.io/xyz") == "userupload"
    assert identify_hoster("https://katfile.com/123/app.rar") == "katfile"
    assert identify_hoster("https://fastupload.io/abc") == "fastupload"
    assert identify_hoster("https://fastupload.co/abc") == "fastupload"
    assert identify_hoster("https://ddownload.com/abc") == "ddownload"
    assert identify_hoster("https://filefactory.com/file/abc") == "filefactory"
    assert identify_hoster("https://turbobit.net/abc.html") == "turbobit"
    assert identify_hoster("https://mediafire.com/file/abc") == "mediafire"
    assert identify_hoster("https://www.mediafire.com/?abc123") == "mediafire"
    assert identify_hoster("https://send.cm/d/abc") == "sendcm"
    assert identify_hoster("https://sendcm.com/d/abc") == "sendcm"
    assert identify_hoster("https://1fichier.com/?abc") == "1fichier"
    assert identify_hoster("https://dailyuploads.net/abc") == "dailyuploads"
    assert identify_hoster("https://dailyuploads.com/abc") == "dailyuploads"
    assert identify_hoster("https://hexupload.net/abc") == "hexupload"
    assert identify_hoster("https://uploadrar.com/abc") == "uploadrar"
    assert identify_hoster("https://zippyshare.com/v/123/file.html") == "zippyshare"
    assert identify_hoster("https://unknownhost.org/download/app.apk") == "generic"
    assert identify_hoster("") == "generic"
    assert identify_hoster(None) == "generic"  # type: ignore


def test_clean_and_unwrap_url():
    """Test unwrapping redirectors and cleaning URL parameters."""
    # anonym.to
    assert (
        clean_and_unwrap_url("https://anonym.to/?https://rapidgator.net/file/123")
        == "https://rapidgator.net/file/123"
    )
    assert (
        clean_and_unwrap_url("http://anonym.to/?http://uploady.io/abc")
        == "http://uploady.io/abc"
    )
    # anonym.click
    assert (
        clean_and_unwrap_url("https://anonym.click/?https://dropgalaxy.in/xyz")
        == "https://dropgalaxy.in/xyz"
    )
    # href.li
    assert (
        clean_and_unwrap_url("https://href.li/?https://mega.nz/file/123")
        == "https://mega.nz/file/123"
    )
    # dereferer.me
    assert (
        clean_and_unwrap_url("https://dereferer.me/?https://katfile.com/123")
        == "https://katfile.com/123"
    )
    # nullrefer.com
    assert (
        clean_and_unwrap_url("https://nullrefer.com/?https://userupload.net/123")
        == "https://userupload.net/123"
    )
    # safelinking.net
    assert (
        clean_and_unwrap_url("https://safelinking.net/p/xyz123?https://userupload.net/456")
        == "https://userupload.net/456"
    )
    # ouo redirect wrapper
    assert (
        clean_and_unwrap_url("http://ouo.io/qs/abc?s=https://rapidgator.net/file/999")
        == "https://rapidgator.net/file/999"
    )
    # generic query param url / dest / target
    assert (
        clean_and_unwrap_url("https://gateway.com/redirect?url=https://uploady.io/foo")
        == "https://uploady.io/foo"
    )
    assert (
        clean_and_unwrap_url("https://gateway.com/out?dest=https://dropgalaxy.in/bar")
        == "https://dropgalaxy.in/bar"
    )
    assert (
        clean_and_unwrap_url("https://gateway.com/click?target=https://fastupload.io/baz")
        == "https://fastupload.io/baz"
    )
    # HTML entities decoding
    assert (
        clean_and_unwrap_url("https://rapidgator.net/file/123?foo=1&amp;bar=2")
        == "https://rapidgator.net/file/123?foo=1&bar=2"
    )
    # Trailing punctuation / quotes
    assert (
        clean_and_unwrap_url("https://rapidgator.net/file/123\">")
        == "https://rapidgator.net/file/123"
    )
    assert (
        clean_and_unwrap_url("https://rapidgator.net/file/123',")
        == "https://rapidgator.net/file/123"
    )
    assert clean_and_unwrap_url("") == ""
    assert clean_and_unwrap_url(None) == ""  # type: ignore


def test_is_ignored_url():
    """Test URL filtering against ignored domains and schemes."""
    assert is_ignored_url("https://forum.mobilism.org/viewtopic.php?t=123") is True
    assert is_ignored_url("http://mobilism.me/test") is True
    assert is_ignored_url("https://play.google.com/store/apps/details?id=test") is True
    assert is_ignored_url("https://postimg.cc/image123") is True
    assert is_ignored_url("ftp://server/file.apk") is True
    assert is_ignored_url("javascript:void(0)") is True
    assert is_ignored_url("https://rapidgator.net/file/123") is False
    assert is_ignored_url("invalid-url") is True


@pytest.mark.asyncio
async def test_extract_from_html_standard_topic():
    """Test link extraction from standard Mobilism post HTML."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Nova Launcher Prime v8.0.18</title></head>
    <body>
      <div id="page-body">
        <div class="postbody">
          <div class="content">
            <span style="font-weight: bold">Nova Launcher Prime v8.0.18 [Mod]</span><br />
            <span style="color: #0080FF"><span style="font-weight: bold">Requirements:</span></span> 8.0 and up<br />
            <span style="color: #0080FF"><span style="font-weight: bold">Overview:</span></span> Nova Launcher replaces your home screen.<br /><br />
            <span style="color: #BF0000"><span style="font-weight: bold">Download Instructions:</span></span><br />
            <a class="postlink" href="https://anonym.to/?https://uploady.io/abc123xyz">https://uploady.io/abc123xyz</a><br /><br />
            <span style="color: #BF0000"><span style="font-weight: bold">Mirrors:</span></span><br />
            <a class="postlink" href="https://dropgalaxy.in/dg123">DropGalaxy</a><br />
            <a class="postlink" href="https://rapidgator.net/file/rg123/nova.apk.html">Rapidgator</a><br />
            <a class="postlink" href="https://mega.nz/file/mg123#key">Mega</a><br />
            <a class="postlink" href="https://userupload.net/uu123">UserUpload</a><br />
          </div>
        </div>
      </div>
    </body>
    </html>
    """
    extractor = MobilismExtractor()
    links = await extractor.extract_from_html(html_content)

    assert len(links) == 5
    urls = [link.url for link in links]
    assert "https://uploady.io/abc123xyz" in urls
    assert "https://dropgalaxy.in/dg123" in urls
    assert "https://rapidgator.net/file/rg123/nova.apk.html" in urls
    assert "https://mega.nz/file/mg123#key" in urls
    assert "https://userupload.net/uu123" in urls

    # Check hosters
    hosters = {link.url: link.hoster for link in links}
    assert hosters["https://uploady.io/abc123xyz"] == "uploady"
    assert hosters["https://dropgalaxy.in/dg123"] == "dropgalaxy"
    assert hosters["https://rapidgator.net/file/rg123/nova.apk.html"] == "rapidgator"
    assert hosters["https://mega.nz/file/mg123#key"] == "mega"
    assert hosters["https://userupload.net/uu123"] == "userupload"

    # Verify priority ordering (lower number = higher priority)
    mega_link = next(l for l in links if l.hoster == "mega")
    rg_link = next(l for l in links if l.hoster == "rapidgator")
    assert mega_link.priority <= rg_link.priority


@pytest.mark.asyncio
async def test_extract_from_html_custom_priorities():
    """Test extractor with custom priority map."""
    html_content = """
    <div class="content">
      <a href="https://mega.nz/file/1">Mega</a>
      <a href="https://rapidgator.net/file/2">Rapidgator</a>
    </div>
    """
    custom_priorities = {"rapidgator": 5, "mega": 50, "generic": 100}
    extractor = MobilismExtractor(hoster_priorities=custom_priorities)
    links = await extractor.extract_from_html(html_content)

    assert len(links) == 2
    assert links[0].hoster == "rapidgator"
    assert links[0].priority == 5
    assert links[1].hoster == "mega"
    assert links[1].priority == 50


@pytest.mark.asyncio
async def test_extract_from_html_plain_text_urls():
    """Test link extraction when URLs are present in plain text without anchor tags."""
    html_content = """
    <div class="content">
      Download Instructions:
      https://userupload.net/plain123

      Mirrors:
      https://fastupload.io/fu_plain456
      https://ddownload.com/dd_plain789
    </div>
    """
    extractor = MobilismExtractor()
    links = await extractor.extract_from_html(html_content)

    assert len(links) == 3
    urls = [l.url for l in links]
    assert "https://userupload.net/plain123" in urls
    assert "https://fastupload.io/fu_plain456" in urls
    assert "https://ddownload.com/dd_plain789" in urls


@pytest.mark.asyncio
async def test_extract_from_html_filters_forum_and_store_links():
    """Test that forum internal navigation and Google Play links are ignored."""
    html_content = """
    <div class="content">
      <a href="https://forum.mobilism.org/viewtopic.php?f=398&t=54321">Topic 54321</a>
      <a href="https://forum.mobilism.org/memberlist.php?mode=viewprofile&u=100">User Profile</a>
      <a href="https://play.google.com/store/apps/details?id=com.example.app">Google Play Store</a>
      <a href="https://anonym.to/?https://rapidgator.net/file/123/app.apk">Rapidgator Download</a>
    </div>
    """
    extractor = MobilismExtractor()
    links = await extractor.extract_from_html(html_content)

    assert len(links) == 1
    assert links[0].url == "https://rapidgator.net/file/123/app.apk"
    assert links[0].hoster == "rapidgator"


@pytest.mark.asyncio
async def test_extract_from_html_deduplication():
    """Test deduplication of repeated links."""
    html_content = """
    <div class="content">
      <a href="https://uploady.io/dup123">Uploady Link</a>
      <p>Mirror: https://uploady.io/dup123</p>
      <a href="https://anonym.to/?https://uploady.io/dup123">Mirror 2</a>
      <a href="https://katfile.com/kf123">KatFile</a>
    </div>
    """
    extractor = MobilismExtractor()
    links = await extractor.extract_from_html(html_content)

    assert len(links) == 2
    urls = [l.url for l in links]
    assert urls.count("https://uploady.io/dup123") == 1
    assert "https://katfile.com/kf123" in urls


@pytest.mark.asyncio
async def test_extract_from_html_empty_and_malformed():
    """Test empty, malformed, or none HTML handling."""
    extractor = MobilismExtractor()
    assert await extractor.extract_from_html("") == []
    assert await extractor.extract_from_html(None) == []  # type: ignore
    assert await extractor.extract_from_html("<html><body><p>No links here</p></body></html>") == []
    assert await extractor.extract_from_html("<<<invalid html>>>") == []


@pytest.mark.asyncio
async def test_fetch_and_extract_direct_success():
    """Test direct fetch_and_extract with mock httpx.AsyncClient."""
    mock_html = """
    <div class="postbody">
      <a href="https://rapidgator.net/file/999/app.apk">Rapidgator</a>
      <a href="https://mega.nz/file/888#key">Mega</a>
    </div>
    """
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    extractor = MobilismExtractor()
    links = await extractor.fetch_and_extract("https://forum.mobilism.org/viewtopic.php?t=12345", client=mock_client)

    assert len(links) == 2
    mock_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_extract_default_client():
    """Test fetch_and_extract creates and closes its own client when client=None."""
    mock_html = "<div class='postbody'><a href='https://mega.nz/file/test'>Mega</a></div>"
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get.return_value = mock_resp

    with patch("apkpipe.extractors.mobilism.httpx.AsyncClient", return_value=mock_async_client_instance):
        extractor = MobilismExtractor()
        links = await extractor.fetch_and_extract("https://forum.mobilism.org/viewtopic.php?t=55555")

        assert len(links) == 1
        assert links[0].url == "https://mega.nz/file/test"
        mock_async_client_instance.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_and_extract_cloudflare_fallback_to_scraper():
    """Test fetch_and_extract falling back to scraper client when Cloudflare challenge is encountered."""
    cf_html = """
    <!DOCTYPE html>
    <html>
      <head><title>Just a moment...</title></head>
      <body>
        <div class="cf-browser-verification">Please wait while your request is verified...</div>
      </body>
    </html>
    """
    solved_html = """
    <div class="postbody">
      <a href="https://dropgalaxy.in/solved123">DropGalaxy</a>
    </div>
    """
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = cf_html

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    mock_scraper = AsyncMock(spec=PlaywrightScraperClient)
    mock_scraper.render_page.return_value = solved_html

    extractor = MobilismExtractor(scraper_client=mock_scraper)
    links = await extractor.fetch_and_extract("https://forum.mobilism.org/viewtopic.php?t=12345", client=mock_client)

    assert len(links) == 1
    assert links[0].url == "https://dropgalaxy.in/solved123"
    assert links[0].hoster == "dropgalaxy"
    mock_scraper.render_page.assert_awaited_once_with("https://forum.mobilism.org/viewtopic.php?t=12345", client=mock_client)


@pytest.mark.asyncio
async def test_fetch_and_extract_http_error_no_scraper():
    """Test fetch_and_extract raises or returns empty when HTTP fails and no scraper client is available."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    extractor = MobilismExtractor(scraper_client=None)
    with pytest.raises(httpx.HTTPStatusError):
        await extractor.fetch_and_extract("https://forum.mobilism.org/viewtopic.php?t=99999", client=mock_client)


@pytest.mark.asyncio
async def test_base_extractor_dummy_implementation():
    """Test dummy extractor implementing BaseExtractor."""
    dummy = DummyExtractor()
    assert await dummy.extract_from_html("test") == []
    assert await dummy.fetch_and_extract("https://test.com") == []
