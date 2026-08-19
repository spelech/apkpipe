"""Notification service integrating Apprise and Ntfy for download lifecycle events."""

from enum import Enum
import logging
from typing import List, Optional
import httpx

from apkpipe.config import get_settings

logger = logging.getLogger(__name__)


class NotificationEvent(str, Enum):
    """Notification event types in the APKPipe lifecycle."""

    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    FEED_MATCHED = "feed_matched"


class NotificationSeverity(str, Enum):
    """Severity levels for notification routing and styling."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"


def format_bytes(size_bytes: Optional[int]) -> str:
    """Format byte size into human-readable representation."""
    if size_bytes is None:
        return "Unknown size"
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


class NotificationService:
    """Dispatches notifications across configured homelab channels (Apprise & Ntfy)."""

    def __init__(
        self,
        apprise_url: Optional[str] = None,
        ntfy_url: Optional[str] = None,
        ntfy_topic: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialize NotificationService.

        Args:
            apprise_url: Target Apprise endpoint (e.g. http://apprise:8000/notify).
            ntfy_url: Base Ntfy server URL (default: https://ntfy.sh).
            ntfy_topic: Ntfy topic identifier.
            http_client: Optional existing AsyncClient instance.
            timeout: HTTP timeout in seconds.
        """
        settings = get_settings()
        self.apprise_url = apprise_url if apprise_url is not None else settings.apprise_url
        self.ntfy_topic = ntfy_topic if ntfy_topic is not None else settings.ntfy_topic
        self.ntfy_url = ntfy_url if ntfy_url is not None else "https://ntfy.sh"
        self._external_client = http_client
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Return True if at least one notification endpoint is configured."""
        return bool(self.apprise_url or self.ntfy_topic)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an HTTP client."""
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=self.timeout)

    async def send_apprise(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        severity: str = NotificationSeverity.INFO,
    ) -> bool:
        """Dispatch notification to Apprise HTTP server.

        Args:
            title: Alert title.
            body: Alert body (supports markdown).
            tags: List of notification tags / category identifiers.
            severity: Severity level (info, success, warning, failure).

        Returns:
            True if notification was delivered, False otherwise.
        """
        if not self.apprise_url:
            return False

        severity_val = severity.value if isinstance(severity, Enum) else str(severity)
        payload = {
            "title": title,
            "body": body,
            "type": severity_val,
            "tag": ",".join(tags) if tags else "all",
            "format": "markdown",
        }

        client = await self._get_client()
        should_close = self._external_client is None
        try:
            response = await client.post(self.apprise_url, json=payload, timeout=self.timeout)
            if response.is_success:
                logger.info("Sent Apprise alert: %s (%s)", title, severity)
                return True
            else:
                logger.warning(
                    "Apprise endpoint returned status %d: %s",
                    response.status_code,
                    response.text,
                )
                return False
        except (httpx.HTTPError, httpx.RequestError, Exception) as exc:
            logger.warning("Failed to dispatch Apprise alert: %s", exc)
            return False
        finally:
            if should_close:
                await client.aclose()

    async def send_ntfy(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        priority: Optional[str] = None,
        click: Optional[str] = None,
    ) -> bool:
        """Dispatch notification to direct Ntfy topic endpoint.

        Args:
            title: Notification title.
            body: Notification body content.
            tags: List of emoji / tags (e.g. ['package', 'white_check_mark']).
            priority: Ntfy priority (e.g. 'default', 'high', 'urgent', 'low', 'min').
            click: Optional URL to open when clicking the alert.

        Returns:
            True if delivered successfully, False otherwise.
        """
        if not self.ntfy_topic:
            return False

        url = f"{self.ntfy_url.rstrip('/')}/{self.ntfy_topic.lstrip('/')}"
        headers = {
            "Title": title,
            "Markdown": "yes",
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if priority:
            headers["Priority"] = priority
        if click:
            headers["Click"] = click

        client = await self._get_client()
        should_close = self._external_client is None
        try:
            response = await client.post(
                url,
                content=body.encode("utf-8"),
                headers=headers,
                timeout=self.timeout,
            )
            if response.is_success:
                logger.info("Sent Ntfy alert to topic '%s': %s", self.ntfy_topic, title)
                return True
            else:
                logger.warning(
                    "Ntfy endpoint returned status %d: %s",
                    response.status_code,
                    response.text,
                )
                return False
        except (httpx.HTTPError, httpx.RequestError, Exception) as exc:
            logger.warning("Failed to dispatch Ntfy alert to topic '%s': %s", self.ntfy_topic, exc)
            return False
        finally:
            if should_close:
                await client.aclose()

    async def send_notification(
        self,
        title: str,
        body: str,
        event_type: str = NotificationEvent.DOWNLOAD_COMPLETED,
        tags: Optional[List[str]] = None,
        severity: str = NotificationSeverity.INFO,
        **kwargs,
    ) -> bool:
        """Dispatch notification to all configured destinations.

        Args:
            title: Alert title.
            body: Alert content.
            event_type: Type of event triggering the notification.
            tags: Notification tags or category labels.
            severity: Severity level.
            **kwargs: Extra parameters passed to notification handlers.

        Returns:
            True if dispatched to at least one endpoint, False otherwise.
        """
        if not self.is_configured:
            logger.debug("No notification endpoints configured; skipping dispatch.")
            return False

        results = []

        if self.apprise_url:
            apprise_ok = await self.send_apprise(
                title=title,
                body=body,
                tags=tags,
                severity=severity,
            )
            results.append(apprise_ok)

        if self.ntfy_topic:
            # Map severity to Ntfy priority if not specified
            priority = kwargs.get("priority")
            if not priority:
                if severity in (NotificationSeverity.FAILURE, "error", "critical"):
                    priority = "high"
                elif severity == NotificationSeverity.SUCCESS:
                    priority = "default"
                else:
                    priority = "default"

            ntfy_ok = await self.send_ntfy(
                title=title,
                body=body,
                tags=tags,
                priority=priority,
                click=kwargs.get("click"),
            )
            results.append(ntfy_ok)

        return any(results)

    async def notify_download_started(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        feed_title: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send notification when a download task begins."""
        version_str = f" v{version}" if version else ""
        releaser_str = f" by [{releaser}]" if releaser else ""
        title = f"[APKPipe] Download Started: {app_name}{version_str}"
        body = f"⏳ Starting download for **{app_name}**{version_str}{releaser_str}."
        if feed_title:
            body += f"\n- Feed: *{feed_title}*"

        tags = ["hourglass_flowing_sand", "apkpipe"]
        return await self.send_notification(
            title=title,
            body=body,
            event_type=NotificationEvent.DOWNLOAD_STARTED,
            tags=tags,
            severity=NotificationSeverity.INFO,
            **kwargs,
        )

    async def notify_download_completed(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        target_path: Optional[str] = None,
        file_size: Optional[int] = None,
        download_tier: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send notification when an APK download completes and is organized."""
        version_str = f" v{version}" if version else ""
        releaser_str = f" by [{releaser}]" if releaser else ""
        title = f"[APKPipe] Download Complete: {app_name}{version_str}"

        size_str = format_bytes(file_size)
        lines = [
            f"✅ Successfully downloaded **{app_name}**{version_str}{releaser_str}.",
        ]
        if target_path:
            lines.append(f"- Destination: `{target_path}`")
        if file_size is not None:
            lines.append(f"- Size: {size_str}")
        if download_tier:
            lines.append(f"- Resolver Tier: `{download_tier}`")

        body = "\n".join(lines)
        tags = ["package", "white_check_mark", "apkpipe"]
        return await self.send_notification(
            title=title,
            body=body,
            event_type=NotificationEvent.DOWNLOAD_COMPLETED,
            tags=tags,
            severity=NotificationSeverity.SUCCESS,
            **kwargs,
        )

    async def notify_download_failed(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        error: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send alert when a download task fails."""
        version_str = f" v{version}" if version else ""
        title = f"[APKPipe] Download Failed: {app_name}{version_str}"
        lines = [
            f"❌ Failed to download **{app_name}**{version_str}.",
        ]
        if error:
            lines.append(f"- Error: {error}")
        if releaser:
            lines.append(f"- Releaser: [{releaser}]")

        body = "\n".join(lines)
        tags = ["warning", "x", "apkpipe"]
        return await self.send_notification(
            title=title,
            body=body,
            event_type=NotificationEvent.DOWNLOAD_FAILED,
            tags=tags,
            severity=NotificationSeverity.FAILURE,
            **kwargs,
        )

    async def notify_feed_matched(
        self,
        app_name: str,
        version: Optional[str] = None,
        releaser: Optional[str] = None,
        feed_title: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Send notification when a release matches watchlist rules."""
        version_str = f" v{version}" if version else ""
        releaser_str = f" [{releaser}]" if releaser else ""
        title = f"[APKPipe] New Release Matched: {app_name}{version_str}"
        lines = [
            f"🔍 Matched watchlist filter for **{app_name}**{version_str}{releaser_str}.",
        ]
        if feed_title:
            lines.append(f"- Feed Item: *{feed_title}*")

        body = "\n".join(lines)
        tags = ["mag", "bell", "apkpipe"]
        return await self.send_notification(
            title=title,
            body=body,
            event_type=NotificationEvent.FEED_MATCHED,
            tags=tags,
            severity=NotificationSeverity.INFO,
            **kwargs,
        )


async def send_notification(
    title: str,
    body: str,
    event_type: str = NotificationEvent.DOWNLOAD_COMPLETED,
    tags: Optional[List[str]] = None,
    severity: str = NotificationSeverity.INFO,
    **kwargs,
) -> bool:
    """Global helper function to dispatch notifications via default settings."""
    service = NotificationService()
    return await service.send_notification(
        title=title,
        body=body,
        event_type=event_type,
        tags=tags,
        severity=severity,
        **kwargs,
    )
