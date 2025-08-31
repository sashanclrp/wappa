"""
Messenger factory for creating platform-specific IMessenger implementations.

This factory implements the Strategy Pattern to create appropriate IMessenger
instances based on platform type, handling all dependency injection and
configuration for each platform-specific messenger.
"""

from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.services.tenant_credentials_service import TenantCredentialsService
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient
from wappa.messaging.whatsapp.handlers.whatsapp_interactive_handler import (
    WhatsAppInteractiveHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_specialized_handler import (
    WhatsAppSpecializedHandler,
)
from wappa.messaging.whatsapp.handlers.whatsapp_template_handler import (
    WhatsAppTemplateHandler,
)
from wappa.messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    import aiohttp


class MessengerFactory:
    """
    Factory for creating platform-specific messenger implementations.

    Uses Strategy Pattern to provide appropriate IMessenger implementations
    based on platform type. Handles dependency injection and configuration
    for each platform-specific messenger.

    Currently supported platforms:
    - WhatsApp Business API

    Future platforms:
    - Telegram Bot API
    - Microsoft Teams
    - Discord
    """

    def __init__(self, http_session: "aiohttp.ClientSession" = None):
        """
        Initialize the messenger factory.

        Args:
            http_session: Shared HTTP session for efficient connection pooling
        """
        self._http_session = http_session
        self.logger = get_logger(__name__)

        # Cache for created messengers to avoid recreating for same tenant/platform
        self._messenger_cache: dict[str, IMessenger] = {}

    async def create_messenger(
        self, platform: PlatformType, tenant_id: str, force_recreate: bool = False
    ) -> IMessenger:
        """
        Create platform-specific messenger implementation.

        Args:
            platform: Platform type (WHATSAPP, TELEGRAM, etc.)
            tenant_id: Tenant-specific identifier
            force_recreate: Force creation of new instance even if cached

        Returns:
            Configured IMessenger implementation for the specified platform

        Raises:
            ValueError: If platform is not supported
            RuntimeError: If messenger creation fails
        """
        cache_key = f"{platform.value}:{tenant_id}"

        # Return cached instance if available and not forcing recreation
        if not force_recreate and cache_key in self._messenger_cache:
            self.logger.debug(f"Using cached messenger for {cache_key}")
            return self._messenger_cache[cache_key]

        self.logger.debug(
            f"Creating new messenger for platform: {platform.value}, tenant: {tenant_id}"
        )

        try:
            if platform == PlatformType.WHATSAPP:
                messenger = await self._create_whatsapp_messenger(tenant_id)

            # Future platform implementations:
            # elif platform == PlatformType.TELEGRAM:
            #     messenger = await self._create_telegram_messenger(tenant_id)
            # elif platform == PlatformType.TEAMS:
            #     messenger = await self._create_teams_messenger(tenant_id)

            else:
                raise ValueError(f"Unsupported platform: {platform.value}")

            # Cache the created messenger
            self._messenger_cache[cache_key] = messenger

            return messenger

        except Exception as e:
            self.logger.error(
                f"Failed to create messenger for platform {platform.value}: {e}"
            )
            raise RuntimeError(f"Messenger creation failed: {e}") from e

    async def _create_whatsapp_messenger(self, tenant_id: str) -> WhatsAppMessenger:
        """
        Create configured WhatsApp messenger with all dependencies.

        Reuses the existing dependency injection chain from whatsapp_dependencies.py
        to maintain consistency and avoid code duplication.

        Args:
            tenant_id: WhatsApp phone_number_id (tenant identifier)

        Returns:
            Fully configured WhatsAppMessenger instance

        Raises:
            ValueError: If tenant credentials are invalid
        """
        self.logger.debug(f"Creating WhatsApp messenger for tenant: {tenant_id}")

        # Validate tenant credentials
        if not TenantCredentialsService.validate_tenant(tenant_id):
            raise ValueError(f"Invalid or inactive tenant: {tenant_id}")

        # Get tenant-specific access token
        access_token = TenantCredentialsService.get_whatsapp_access_token(tenant_id)

        # Create WhatsApp client (core dependency)
        client = WhatsAppClient(
            session=self._http_session,
            access_token=access_token,
            phone_number_id=tenant_id,
            logger=self.logger,
        )

        # Create all WhatsApp handlers (following dependency injection pattern)
        media_handler = WhatsAppMediaHandler(client=client, tenant_id=tenant_id)
        interactive_handler = WhatsAppInteractiveHandler(
            client=client, tenant_id=tenant_id
        )
        template_handler = WhatsAppTemplateHandler(client=client, tenant_id=tenant_id)
        specialized_handler = WhatsAppSpecializedHandler(
            client=client, tenant_id=tenant_id
        )

        # Create unified WhatsApp messenger with all handlers
        messenger = WhatsAppMessenger(
            client=client,
            media_handler=media_handler,
            interactive_handler=interactive_handler,
            template_handler=template_handler,
            specialized_handler=specialized_handler,
            tenant_id=tenant_id,
        )

        self.logger.info(
            f"✅ WhatsApp messenger created successfully for tenant: {tenant_id}"
        )
        return messenger

    def get_supported_platforms(self) -> list[PlatformType]:
        """
        Get list of currently supported platforms.

        Returns:
            List of supported platform types
        """
        return [PlatformType.WHATSAPP]

    def is_platform_supported(self, platform: PlatformType) -> bool:
        """
        Check if platform is supported by this factory.

        Args:
            platform: Platform type to check

        Returns:
            True if platform is supported, False otherwise
        """
        return platform in self.get_supported_platforms()

    def clear_cache(self, platform: PlatformType = None, tenant_id: str = None):
        """
        Clear messenger cache.

        Args:
            platform: Optional platform to clear (clear all if None)
            tenant_id: Optional tenant to clear (clear all if None)
        """
        if platform and tenant_id:
            # Clear specific platform/tenant combination
            cache_key = f"{platform.value}:{tenant_id}"
            self._messenger_cache.pop(cache_key, None)
            self.logger.debug(f"Cleared messenger cache for {cache_key}")
        elif platform:
            # Clear all messengers for a platform
            to_remove = [
                key
                for key in self._messenger_cache
                if key.startswith(f"{platform.value}:")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug(f"Cleared messenger cache for platform: {platform.value}")
        elif tenant_id:
            # Clear all messengers for a tenant
            to_remove = [
                key for key in self._messenger_cache if key.endswith(f":{tenant_id}")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug(f"Cleared messenger cache for tenant: {tenant_id}")
        else:
            # Clear entire cache
            self._messenger_cache.clear()
            self.logger.debug("Cleared entire messenger cache")

    # Future platform implementations:

    # async def _create_telegram_messenger(self, tenant_id: str) -> IMessenger:
    #     """Create configured Telegram messenger (future implementation)."""
    #     # TODO: Implement Telegram Bot API messenger
    #     raise NotImplementedError("Telegram messenger not yet implemented")

    # async def _create_teams_messenger(self, tenant_id: str) -> IMessenger:
    #     """Create configured Teams messenger (future implementation)."""
    #     # TODO: Implement Microsoft Teams messenger
    #     raise NotImplementedError("Teams messenger not yet implemented")
