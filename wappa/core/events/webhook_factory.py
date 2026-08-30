"""
Webhook URL Factory for generating platform-specific webhook URLs.

Implements the Factory pattern to provide clean, consistent webhook URL generation
for different messaging platforms with payload-derived Inbox routing.
"""

from enum import Enum

from wappa.core.config.settings import settings
from wappa.schemas.core.types import PlatformType


class WebhookEndpointType(Enum):
    """Types of webhook endpoints that can be generated."""

    WEBHOOK = "webhook"  # Main webhook processing endpoint
    VERIFY = "verify"  # Webhook verification endpoint
    STATUS = "status"  # Webhook status check endpoint


class WebhookURLFactory:
    """
    Factory for generating platform-specific webhook URLs.

    Provides consistent URL generation for different messaging platforms
    with support for the canonical payload-routed endpoint.

    Implements the Factory pattern with Builder pattern elements for
    flexible URL construction.
    """

    def __init__(self, base_url: str | None = None):
        """
        Initialize the webhook URL factory.

        Args:
            base_url: Base URL for webhook generation. If None, will be determined
                     from settings or environment.
        """
        self.base_url = base_url or self._determine_base_url()

    def _determine_base_url(self) -> str:
        """
        Determine the base URL for webhook generation.

        Returns:
            Base URL for webhook endpoints
        """
        # In development, use localhost
        if settings.is_development:
            return f"http://localhost:{settings.port}"

        # In production, this would be configured via environment
        # For now, use a placeholder that should be configured
        webhook_base_url = getattr(settings, "webhook_base_url", None)
        if isinstance(webhook_base_url, str) and webhook_base_url:
            return webhook_base_url

        # Default fallback (should be configured in production)
        return "https://your-domain.com"

    def generate_webhook_url(
        self,
        platform: PlatformType,
        endpoint_type: WebhookEndpointType = WebhookEndpointType.WEBHOOK,
    ) -> str:
        """
        Generate the canonical webhook URL for a platform.

        Args:
            platform: The messaging platform (WhatsApp, Telegram, etc.)
            endpoint_type: Type of webhook endpoint to generate

        Returns:
            Complete canonical webhook URL for the platform

        Example:
            >>> factory = WebhookURLFactory()
            >>> factory.generate_webhook_url(PlatformType.WHATSAPP)
            "https://your-domain.com/webhook/inboxes/whatsapp"
        """
        platform_name = platform.value.lower()

        if endpoint_type == WebhookEndpointType.STATUS:
            return f"{self.base_url}/webhook/inboxes/{platform_name}/status"

        return f"{self.base_url}/webhook/inboxes/{platform_name}"

    def generate_whatsapp_webhook_url(self) -> str:
        """
        Generate a WhatsApp-specific webhook URL.

        Returns:
            Canonical WhatsApp webhook URL for GET verification and POST delivery
        """
        return self.generate_webhook_url(PlatformType.WHATSAPP)

    def generate_whatsapp_verify_url(self) -> str:
        """
        Generate a WhatsApp webhook verification URL.

        Returns:
            WhatsApp webhook verification URL
        """
        return self.generate_webhook_url(PlatformType.WHATSAPP)

    def get_supported_platforms(self) -> dict[str, dict[str, str]]:
        """
        Get all supported platforms and their webhook URL patterns.

        Returns:
            Dictionary mapping platform names to their URL patterns
        """
        patterns = {}

        for platform in PlatformType:
            platform_name = platform.value.lower()
            patterns[platform_name] = {
                "webhook_pattern": f"/webhook/inboxes/{platform_name}",
                "verify_pattern": f"/webhook/inboxes/{platform_name}",
                "status_pattern": f"/webhook/inboxes/{platform_name}/status",
                "example_webhook": self.generate_webhook_url(platform),
                "example_verify": self.generate_webhook_url(platform),
            }

        return patterns

    def validate_webhook_url(self, url: str, platform: PlatformType) -> bool:
        """
        Validate if a URL matches the expected webhook pattern for a platform.

        Args:
            url: URL to validate
            platform: Expected platform
        Returns:
            True if URL matches the expected pattern
        """
        expected_url = self.generate_webhook_url(platform)
        return url == expected_url

    def _parse_webhook_path(self, webhook_path: str) -> str | None:
        """Parse a canonical webhook path and return its platform name."""
        path_parts = webhook_path.strip("/").split("/")
        if (
            len(path_parts) in {3, 4}
            and path_parts[:2] == ["webhook", "inboxes"]
            and (len(path_parts) == 3 or path_parts[3] == "status")
        ):
            return path_parts[2]
        return None

    def extract_platform_from_url(self, webhook_path: str) -> PlatformType | None:
        """
        Extract platform type from a webhook URL path.

        Args:
            webhook_path: Webhook URL path (e.g., "/webhook/inboxes/whatsapp")

        Returns:
            PlatformType if found, None otherwise
        """
        parsed = self._parse_webhook_path(webhook_path)
        if parsed is None:
            return None

        try:
            return PlatformType(parsed.lower())
        except ValueError:
            return None


# Global factory instance
webhook_url_factory = WebhookURLFactory()


def get_webhook_url_factory() -> WebhookURLFactory:
    """
    Get the global webhook URL factory instance.

    Returns:
        WebhookURLFactory instance
    """
    return webhook_url_factory
