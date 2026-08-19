"""Headless scraper client for FlareSolverr and Playwright-based scraper services."""

from typing import Any, Dict, List, Optional
import httpx

from apkpipe.config import get_settings


class ScraperError(Exception):
    """Exception raised when page rendering or scraping fails."""

    pass


class PlaywrightScraperClient:
    """Client for rendering pages through FlareSolverr or playwright-csharp-scraper."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        if base_url is None:
            settings = get_settings()
            base_url = settings.scraper_url or "http://scraper:8080"
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def render_page(
        self,
        url: str,
        client: Optional[httpx.AsyncClient] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Render target URL via scraper service and return solved HTML."""
        eff_timeout = timeout or self.timeout
        should_close = False

        if client is None:
            client = httpx.AsyncClient(timeout=eff_timeout)
            should_close = True

        try:
            # 1. Try standard FlareSolverr v1 protocol
            endpoint_v1 = f"{self.base_url}/v1"
            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": int(eff_timeout * 1000),
            }

            resp = await client.post(
                endpoint_v1,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=eff_timeout,
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "error":
                    msg = data.get("message", "Unknown scraper error")
                    raise ScraperError(f"Scraper error: {msg}")

                solution = data.get("solution") or {}
                if isinstance(solution, dict) and "response" in solution:
                    return str(solution["response"])
                if isinstance(solution, dict) and "html" in solution:
                    return str(solution["html"])
                if "html" in data:
                    return str(data["html"])
                return resp.text

            if resp.status_code == 404:
                # 2. Try generic /render endpoint
                endpoint_render = f"{self.base_url}/render"
                resp_render = await client.post(
                    endpoint_render,
                    json={"url": url},
                    headers={"Content-Type": "application/json"},
                    timeout=eff_timeout,
                )
                if resp_render.status_code == 200:
                    try:
                        render_data = resp_render.json()
                        if isinstance(render_data, dict) and "html" in render_data:
                            return str(render_data["html"])
                    except Exception:
                        pass
                    return resp_render.text
                raise ScraperError(f"Scraper returned status code {resp_render.status_code}")

            # Non-200 / non-404 status
            try:
                err_data = resp.json()
                msg = err_data.get("message") or resp.text
            except Exception:
                msg = resp.text
            raise ScraperError(f"Scraper error (status {resp.status_code}): {msg}")

        except httpx.RequestError as exc:
            raise ScraperError(f"Failed to connect to scraper at {self.base_url}: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()

    async def health_check(
        self,
        client: Optional[httpx.AsyncClient] = None,
    ) -> bool:
        """Check if scraper endpoint is reachable and responsive."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            should_close = True

        try:
            resp = await client.get(f"{self.base_url}/", timeout=10.0)
            return resp.status_code < 400
        except Exception:
            return False
        finally:
            if should_close:
                await client.aclose()

    async def get_cookies(
        self,
        url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, str]:
        """Extract cookies resolved by FlareSolverr for the target URL."""
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout)
            should_close = True

        try:
            endpoint_v1 = f"{self.base_url}/v1"
            payload = {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": int(self.timeout * 1000),
            }

            resp = await client.post(
                endpoint_v1,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )

            if resp.status_code != 200:
                raise ScraperError(f"Scraper returned status {resp.status_code}")

            data = resp.json()
            solution = data.get("solution") or {}
            raw_cookies: List[Dict[str, Any]] = solution.get("cookies") or []

            cookie_dict: Dict[str, str] = {}
            for c in raw_cookies:
                name = c.get("name")
                val = c.get("value")
                if name is not None and val is not None:
                    cookie_dict[str(name)] = str(val)

            return cookie_dict
        except httpx.RequestError as exc:
            raise ScraperError(f"Failed to fetch cookies from scraper: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()
