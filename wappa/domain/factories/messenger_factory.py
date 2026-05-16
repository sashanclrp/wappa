"""Factory for creating platform-specific IMessenger implementations."""

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
    import httpx


class MessengerFactory:
    """Factory for creating platform-specific messenger implementations."""

    def __init__(self, http_session: "httpx.AsyncClient" = None) -> None:
        self._http_session = http_session
        self.logger = get_logger(__name__)
        self._messenger_cache: dict[str, IMessenger] = {}

    async def create_messenger(
        self, platform: PlatformType, tenant_id: str, force_recreate: bool = False
    ) -> IMessenger:
        cache_key = f"{platform.value}:{tenant_id}"

        if not force_recreate and cache_key in self._messenger_cache:
            self.logger.debug(f"Using cached messenger for {cache_key}")
            return self._messenger_cache[cache_key]

        self.logger.debug(
            f"Creating new messenger for platform: {platform.value}, tenant: {tenant_id}"
        )

        try:
            if platform == PlatformType.WHATSAPP:
                messenger = await self._create_whatsapp_messenger(tenant_id)
            else:
                raise ValueError(f"Unsupported platform: {platform.value}")

            self._messenger_cache[cache_key] = messenger
            return messenger

        except Exception as e:
            self.logger.error(
                f"Failed to create messenger for platform {platform.value}: {e}"
            )
            raise RuntimeError(f"Messenger creation failed: {e}") from e

    async def _create_whatsapp_messenger(self, tenant_id: str) -> WhatsAppMessenger:
        self.logger.debug(f"Creating WhatsApp messenger for tenant: {tenant_id}")

        if not TenantCredentialsService.validate_tenant(tenant_id):
            raise ValueError(f"Invalid or inactive tenant: {tenant_id}")

        access_token = TenantCredentialsService.get_whatsapp_access_token(tenant_id)

        client = WhatsAppClient(
            session=self._http_session,
            access_token=access_token,
            phone_number_id=tenant_id,
            logger=self.logger,
        )

        messenger = WhatsAppMessenger(
            client=client,
            media_handler=WhatsAppMediaHandler(client=client, tenant_id=tenant_id),
            interactive_handler=WhatsAppInteractiveHandler(
                client=client, tenant_id=tenant_id
            ),
            template_handler=WhatsAppTemplateHandler(client=client, tenant_id=tenant_id),
            specialized_handler=WhatsAppSpecializedHandler(
                client=client, tenant_id=tenant_id
            ),
            tenant_id=tenant_id,
        )

        self.logger.info(
            f"✅ WhatsApp messenger created successfully for tenant: {tenant_id}"
        )
        return messenger

    def get_supported_platforms(self) -> list[PlatformType]:
        return [PlatformType.WHATSAPP]

    def is_platform_supported(self, platform: PlatformType) -> bool:
        return platform in self.get_supported_platforms()

    def clear_cache(
        self, platform: PlatformType = None, tenant_id: str = None
    ) -> None:
        if platform and tenant_id:
            cache_key = f"{platform.value}:{tenant_id}"
            self._messenger_cache.pop(cache_key, None)
            self.logger.debug(f"Cleared messenger cache for {cache_key}")
        elif platform:
            to_remove = [
                key
                for key in self._messenger_cache
                if key.startswith(f"{platform.value}:")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug(f"Cleared messenger cache for platform: {platform.value}")
        elif tenant_id:
            to_remove = [
                key for key in self._messenger_cache if key.endswith(f":{tenant_id}")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug(f"Cleared messenger cache for tenant: {tenant_id}")
        else:
            self._messenger_cache.clear()
            self.logger.debug("Cleared entire messenger cache")
