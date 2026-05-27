"""Factory for creating platform-specific IMessenger implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.inbox_credential_store import IInboxCredentialStore
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.session_provider import HTTPSessionClosedError
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

    def __init__(
        self,
        session_provider: Callable[[], httpx.AsyncClient],
        credential_store: IInboxCredentialStore | None = None,
    ) -> None:
        self._session_provider = session_provider
        self._credential_store = credential_store
        self.logger = get_logger(__name__)
        self._messenger_cache: dict[str, IMessenger] = {}

    def _get_session(self) -> httpx.AsyncClient:
        """Return the HTTP session via the lifecycle-aware provider."""
        return self._session_provider()

    async def create_messenger(
        self, platform: PlatformType, inbox_id: str, force_recreate: bool = False
    ) -> IMessenger:
        cache_key = f"{platform.value}:{inbox_id}"

        if not force_recreate and cache_key in self._messenger_cache:
            try:
                self._get_session()
                self.logger.debug("Using cached messenger for %s", cache_key)
                return self._messenger_cache[cache_key]
            except HTTPSessionClosedError:
                self.logger.warning(
                    "Cached messenger for %s has stale session, evicting", cache_key
                )
                del self._messenger_cache[cache_key]

        self.logger.debug(
            "Creating new messenger for platform: %s, inbox: %s",
            platform.value,
            inbox_id,
        )

        try:
            if platform == PlatformType.WHATSAPP:
                messenger = await self._create_whatsapp_messenger(inbox_id)
            else:
                raise ValueError(f"Unsupported platform: {platform.value}")

            self._messenger_cache[cache_key] = messenger
            return messenger

        except Exception as e:
            self.logger.error(
                "Failed to create messenger for platform %s: %s", platform.value, e
            )
            raise RuntimeError(f"Messenger creation failed: {e}") from e

    async def _create_whatsapp_messenger(self, inbox_id: str) -> WhatsAppMessenger:
        self.logger.debug("Creating WhatsApp messenger for inbox: %s", inbox_id)

        if self._credential_store is None:
            raise RuntimeError(
                "MessengerFactory._credential_store is None — cannot resolve "
                f"credentials for inbox '{inbox_id}'. Ensure an "
                "IInboxCredentialStore is wired (check WappaBuilder or "
                "InboundRuntime dependency construction)."
            )

        session = self._get_session()

        if not await self._credential_store.validate_inbox(inbox_id):
            raise ValueError(f"Invalid or inactive inbox: {inbox_id}")

        credentials = await self._credential_store.get_credentials(inbox_id)

        client = WhatsAppClient(
            session=session,
            access_token=credentials.access_token,
            phone_number_id=inbox_id,
            logger=self.logger,
        )

        messenger = WhatsAppMessenger(
            client=client,
            media_handler=WhatsAppMediaHandler(client=client, inbox_id=inbox_id),
            interactive_handler=WhatsAppInteractiveHandler(
                client=client, inbox_id=inbox_id
            ),
            template_handler=WhatsAppTemplateHandler(client=client, inbox_id=inbox_id),
            specialized_handler=WhatsAppSpecializedHandler(
                client=client, inbox_id=inbox_id
            ),
            inbox_id=inbox_id,
        )

        self.logger.info(
            "✅ WhatsApp messenger created successfully for inbox: %s", inbox_id
        )
        return messenger

    def get_supported_platforms(self) -> list[PlatformType]:
        return [PlatformType.WHATSAPP]

    def is_platform_supported(self, platform: PlatformType) -> bool:
        return platform in self.get_supported_platforms()

    def clear_cache(
        self, platform: PlatformType | None = None, inbox_id: str | None = None
    ) -> None:
        if platform and inbox_id:
            cache_key = f"{platform.value}:{inbox_id}"
            self._messenger_cache.pop(cache_key, None)
            self.logger.debug("Cleared messenger cache for %s", cache_key)
        elif platform:
            to_remove = [
                key
                for key in self._messenger_cache
                if key.startswith(f"{platform.value}:")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug(
                "Cleared messenger cache for platform: %s", platform.value
            )
        elif inbox_id:
            to_remove = [
                key for key in self._messenger_cache if key.endswith(f":{inbox_id}")
            ]
            for key in to_remove:
                del self._messenger_cache[key]
            self.logger.debug("Cleared messenger cache for inbox: %s", inbox_id)
        else:
            self._messenger_cache.clear()
            self.logger.debug("Cleared entire messenger cache")
