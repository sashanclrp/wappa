"""
Webhook URL Factory for generating platform-specific webhook URLs.

Implements the Factory pattern to provide clean, consistent webhook URL generation
for different messaging platforms with tenant-aware routing.
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
    with support for tenant-aware routing and different endpoint types.

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
        if webhook_base_url:
            return webhook_base_url

        # Default fallback (should be configured in production)
        return "https://your-domain.com"

    def generate_webhook_url(
        self,
        platform: PlatformType,
        tenant_id: str,
        endpoint_type: WebhookEndpointType = WebhookEndpointType.WEBHOOK,
    ) -> str:
        """
        Generate a webhook URL for a specific platform and tenant.

        Args:
            platform: The messaging platform (WhatsApp, Telegram, etc.)
            tenant_id: The tenant identifier (phone_number_id for WhatsApp)
            endpoint_type: Type of webhook endpoint to generate

        Returns:
            Complete webhook URL for the platform and tenant

        Example:
            >>> factory = WebhookURLFactory()
            >>> factory.generate_webhook_url(PlatformType.WHATSAPP, "123456789")
            "https://your-domain.com/webhook/messenger/123456789/whatsapp"
        """
        platform_name = platform.value.lower()

        if endpoint_type == WebhookEndpointType.VERIFY:
            return f"{self.base_url}/webhook/messenger/{platform_name}/verify"
        elif endpoint_type == WebhookEndpointType.STATUS:
            return (
                f"{self.base_url}/webhook/messenger/{tenant_id}/{platform_name}/status"
            )
        else:  # WEBHOOK (default)
            return f"{self.base_url}/webhook/messenger/{tenant_id}/{platform_name}"

    def generate_whatsapp_webhook_url(self) -> str:
        """
        Generate a WhatsApp-specific webhook URL.

        Convenience method for WhatsApp webhook generation that automatically
        uses the tenant_id from settings (WP_PHONE_ID from .env).

        Returns:
            Complete WhatsApp webhook URL using configured phone number ID
        """
        return self.generate_webhook_url(PlatformType.WHATSAPP, settings.owner_id)

    def generate_whatsapp_verify_url(self) -> str:
        """
        Generate a WhatsApp webhook verification URL.

        Returns:
            WhatsApp webhook verification URL
        """
        return self.generate_webhook_url(
            PlatformType.WHATSAPP, "", WebhookEndpointType.VERIFY
        )

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
                "webhook_pattern": f"/webhook/messenger/{{tenant_id}}/{platform_name}",
                "verify_pattern": f"/webhook/messenger/{platform_name}/verify",
                "status_pattern": f"/webhook/messenger/{{tenant_id}}/{platform_name}/status",
                "example_webhook": self.generate_webhook_url(platform, "TENANT_ID"),
                "example_verify": self.generate_webhook_url(
                    platform, "", WebhookEndpointType.VERIFY
                ),
            }

        return patterns

    def validate_webhook_url(
        self, url: str, platform: PlatformType, tenant_id: str
    ) -> bool:
        """
        Validate if a URL matches the expected webhook pattern for a platform.

        Args:
            url: URL to validate
            platform: Expected platform
            tenant_id: Expected tenant ID

        Returns:
            True if URL matches the expected pattern
        """
        expected_url = self.generate_webhook_url(platform, tenant_id)
        return url == expected_url

    def _parse_webhook_path(self, webhook_path: str) -> tuple[str, str] | None:
        """
        Parse webhook URL path and extract tenant_id and platform.

        Args:
            webhook_path: Webhook URL path (e.g., "/webhook/messenger/123/whatsapp")

        Returns:
            Tuple of (tenant_id, platform) if valid, None otherwise
        """
        path_parts = webhook_path.strip("/").split("/")

        if (
            len(path_parts) >= 4
            and path_parts[0] == "webhook"
            and path_parts[1] == "messenger"
        ):
            return path_parts[2], path_parts[3]

        return None

    def extract_platform_from_url(self, webhook_path: str) -> PlatformType | None:
        """
        Extract platform type from a webhook URL path.

        Args:
            webhook_path: Webhook URL path (e.g., "/webhook/messenger/123/whatsapp")

        Returns:
            PlatformType if found, None otherwise
        """
        parsed = self._parse_webhook_path(webhook_path)
        if parsed is None:
            return None

        _, platform_name = parsed
        try:
            return PlatformType(platform_name.lower())
        except ValueError:
            return None

    def extract_tenant_from_url(self, webhook_path: str) -> str | None:
        """
        Extract tenant ID from a webhook URL path.

        Args:
            webhook_path: Webhook URL path (e.g., "/webhook/messenger/123/whatsapp")

        Returns:
            Tenant ID if found, None otherwise
        """
        parsed = self._parse_webhook_path(webhook_path)
        if parsed is None:
            return None

        tenant_id, _ = parsed
        return tenant_id


# Global factory instance
webhook_url_factory = WebhookURLFactory()


def get_webhook_url_factory() -> WebhookURLFactory:
    """
    Get the global webhook URL factory instance.

    Returns:
        WebhookURLFactory instance
    """
    return webhook_url_factory
