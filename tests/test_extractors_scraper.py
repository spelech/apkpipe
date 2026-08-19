"""Unit tests for Playwright / FlareSolverr scraper client."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from apkpipe.extractors.scraper_client import PlaywrightScraperClient, ScraperError


def test_scraper_client_init():
    """Test PlaywrightScraperClient initialization and configuration."""
    client = PlaywrightScraperClient(base_url="http://custom-scraper:8428", timeout=45.0)
    assert client.base_url == "http://custom-scraper:8428"
    assert client.timeout == 45.0

    # Default fallback from settings
    with patch("apkpipe.extractors.scraper_client.get_settings") as mock_settings:
        mock_settings.return_value.scraper_url = "http://env-scraper:8080"
        client_default = PlaywrightScraperClient()
        assert client_default.base_url == "http://env-scraper:8080"
        assert client_default.timeout == 60.0

    with patch("apkpipe.extractors.scraper_client.get_settings") as mock_settings:
        mock_settings.return_value.scraper_url = ""
        client_fallback = PlaywrightScraperClient()
        assert client_fallback.base_url == "http://scraper:8080"


@pytest.mark.asyncio
async def test_scraper_render_page_flaresolverr_success():
    """Test successful render_page using FlareSolverr /v1 protocol."""
    mock_payload = {
        "status": "ok",
        "message": "Challenge solved!",
        "solution": {
            "url": "https://forum.mobilism.org/viewtopic.php?t=123",
            "status": 200,
            "response": "<html><body><div class='postbody'>Solved content</div></body></html>",
            "cookies": [{"name": "cf_clearance", "value": "xyz123"}],
        },
        "version": "v3.3.0",
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload
    mock_resp.text = '{"status": "ok"}'

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    html = await scraper.render_page(
        "https://forum.mobilism.org/viewtopic.php?t=123", client=mock_http_client
    )

    assert "<div class='postbody'>Solved content</div>" in html
    mock_http_client.post.assert_awaited_once()
    call_args, call_kwargs = mock_http_client.post.call_args
    assert "http://scraper:8080/v1" in call_args[0]
    assert call_kwargs["json"]["cmd"] == "request.get"
    assert call_kwargs["json"]["url"] == "https://forum.mobilism.org/viewtopic.php?t=123"


@pytest.mark.asyncio
async def test_scraper_render_page_flaresolverr_html_solution_field():
    """Test render_page when solution uses 'html' key or top level 'html' key."""
    # solution['html']
    mock_payload_html = {
        "status": "ok",
        "solution": {"html": "<p>Solution HTML</p>"},
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload_html

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    assert await scraper.render_page("https://example.com", client=mock_http_client) == "<p>Solution HTML</p>"

    # top-level html
    mock_payload_top_html = {"status": "ok", "html": "<div>Top HTML</div>"}
    mock_resp.json.return_value = mock_payload_top_html
    assert await scraper.render_page("https://example.com", client=mock_http_client) == "<div>Top HTML</div>"

    # raw text fallback
    mock_payload_other = {"status": "ok"}
    mock_resp.json.return_value = mock_payload_other
    mock_resp.text = "raw text response"
    assert await scraper.render_page("https://example.com", client=mock_http_client) == "raw text response"


@pytest.mark.asyncio
async def test_scraper_render_page_direct_render_endpoint():
    """Test fallback when scraper provides direct /render or /scrape endpoint."""
    resp_404 = MagicMock(spec=httpx.Response)
    resp_404.status_code = 404

    resp_render = MagicMock(spec=httpx.Response)
    resp_render.status_code = 200
    resp_render.json.return_value = {"html": "<html><body>Rendered HTML</body></html>"}

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.side_effect = [resp_404, resp_render]

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    html = await scraper.render_page(
        "https://forum.mobilism.org/viewtopic.php?t=123", client=mock_http_client
    )

    assert "Rendered HTML" in html
    assert mock_http_client.post.await_count == 2


@pytest.mark.asyncio
async def test_scraper_render_page_direct_render_text_fallback():
    """Test /render endpoint returning raw HTML string instead of JSON."""
    resp_404 = MagicMock(spec=httpx.Response)
    resp_404.status_code = 404

    resp_render = MagicMock(spec=httpx.Response)
    resp_render.status_code = 200
    resp_render.json.side_effect = Exception("Not JSON")
    resp_render.text = "<html>Raw Render</html>"

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.side_effect = [resp_404, resp_render]

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    html = await scraper.render_page("https://example.com", client=mock_http_client)
    assert html == "<html>Raw Render</html>"


@pytest.mark.asyncio
async def test_scraper_render_page_render_endpoint_non_200():
    """Test error when /render endpoint returns non-200."""
    resp_404 = MagicMock(spec=httpx.Response)
    resp_404.status_code = 404

    resp_render = MagicMock(spec=httpx.Response)
    resp_render.status_code = 502

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.side_effect = [resp_404, resp_render]

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    with pytest.raises(ScraperError, match="status code 502"):
        await scraper.render_page("https://example.com", client=mock_http_client)


@pytest.mark.asyncio
async def test_scraper_render_page_default_client():
    """Test render_page instantiates and closes internal client when client is None."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "solution": {"response": "<html>Auto client</html>"}}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("apkpipe.extractors.scraper_client.httpx.AsyncClient", return_value=mock_client):
        scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
        res = await scraper.render_page("https://test.com")
        assert res == "<html>Auto client</html>"
        mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scraper_render_page_flaresolverr_error_status():
    """Test error raised when FlareSolverr returns error status."""
    mock_payload = {
        "status": "error",
        "message": "Error: Captcha solve timeout",
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload
    mock_resp.text = '{"status": "error"}'

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    with pytest.raises(ScraperError, match="Captcha solve timeout"):
        await scraper.render_page(
            "https://forum.mobilism.org/viewtopic.php?t=123", client=mock_http_client
        )


@pytest.mark.asyncio
async def test_scraper_render_page_500_status():
    """Test non-200 non-404 status from scraper."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.json.return_value = {"message": "Internal crash"}
    mock_resp.text = "Internal crash"

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    with pytest.raises(ScraperError, match="status 500"):
        await scraper.render_page("https://example.com", client=mock_http_client)


@pytest.mark.asyncio
async def test_scraper_render_page_network_exception():
    """Test handling when network connection to scraper fails."""
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.side_effect = httpx.ConnectError("Connection refused")

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    with pytest.raises(ScraperError, match="Connection refused"):
        await scraper.render_page(
            "https://forum.mobilism.org/viewtopic.php?t=123", client=mock_http_client
        )


@pytest.mark.asyncio
async def test_scraper_health_check_success():
    """Test scraper health_check returns True on successful ping."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok", "version": "v3.3.0"}

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    healthy = await scraper.health_check(client=mock_http_client)
    assert healthy is True


@pytest.mark.asyncio
async def test_scraper_health_check_default_client():
    """Test health_check creates and closes its own client when client=None."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with patch("apkpipe.extractors.scraper_client.httpx.AsyncClient", return_value=mock_client):
        scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
        assert await scraper.health_check() is True
        mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scraper_health_check_failure():
    """Test scraper health_check returns False on connection error or non-200."""
    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.get.side_effect = httpx.ConnectError("Failed")

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    healthy = await scraper.health_check(client=mock_http_client)
    assert healthy is False


@pytest.mark.asyncio
async def test_scraper_get_cookies_success():
    """Test extracting cookies via get_cookies."""
    mock_payload = {
        "status": "ok",
        "solution": {
            "cookies": [
                {"name": "cf_clearance", "value": "token123"},
                {"name": "session_id", "value": "abc456"},
            ],
            "response": "<html></html>",
        },
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    cookies = await scraper.get_cookies(
        "https://forum.mobilism.org", client=mock_http_client
    )

    assert cookies == {"cf_clearance": "token123", "session_id": "abc456"}


@pytest.mark.asyncio
async def test_scraper_get_cookies_default_client():
    """Test get_cookies creates and closes its own client when client=None."""
    mock_payload = {
        "status": "ok",
        "solution": {
            "cookies": [{"name": "cf_clearance", "value": "val999"}],
        },
    }
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp

    with patch("apkpipe.extractors.scraper_client.httpx.AsyncClient", return_value=mock_client):
        scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
        cookies = await scraper.get_cookies("https://forum.mobilism.org")
        assert cookies == {"cf_clearance": "val999"}
        mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_scraper_get_cookies_errors():
    """Test get_cookies handling error status code and request exception."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500

    mock_http_client = AsyncMock(spec=httpx.AsyncClient)
    mock_http_client.post.return_value = mock_resp

    scraper = PlaywrightScraperClient(base_url="http://scraper:8080")
    with pytest.raises(ScraperError, match="status 500"):
        await scraper.get_cookies("https://forum.mobilism.org", client=mock_http_client)

    mock_http_client.post.side_effect = httpx.ConnectError("Failed")
    with pytest.raises(ScraperError, match="Failed to fetch cookies"):
        await scraper.get_cookies("https://forum.mobilism.org", client=mock_http_client)
