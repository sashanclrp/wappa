"""Factory for creating platform-specific IMessenger implementations."""

from __future__ import annotations

import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.errors import InboxDirectoryError
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
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
    """Build and cache one Messenger per qualified Inbox.

    Credentials come from the internal ``IInboxCredentialResolver`` or from a
    ``ResolvedInboxCredentials`` value the caller already holds. Directory
    failures propagate as their typed categories; they are never reported as
    an unknown Inbox or an unclassified runtime error.
    """

    def __init__(
        self,
        session_provider: Callable[[], httpx.AsyncClient],
        media_download_client_provider: Callable[[], httpx.AsyncClient],
        credential_resolver: IInboxCredentialResolver | None = None,
    ) -> None:
        self._session_provider = session_provider
        self._credential_resolver = credential_resolver
        self._media_download_client_provider = media_download_client_provider
        self.logger = get_logger(__name__)
        self._messenger_cache: dict[str, IMessenger] = {}
        if credential_resolver is not None:
            self_ref = weakref.ref(self)

            def _on_evict(inbox_ref: InboxRef) -> None:
                factory = self_ref()
                if factory is not None:
                    factory.evict(inbox_ref)

            credential_resolver.subscribe_evictions(_on_evict)

    def _get_session(self) -> httpx.AsyncClient:
        """Return the HTTP session via the lifecycle-aware provider."""
        return self._session_provider()

    def _get_media_download_client(self) -> httpx.AsyncClient:
        return self._media_download_client_provider()

    @staticmethod
    def _cache_key(inbox_ref: InboxRef) -> str:
        return str(inbox_ref)

    async def create_messenger(
        self,
        inbox_ref: InboxRef,
        *,
        credentials: ResolvedInboxCredentials | None = None,
        force_recreate: bool = False,
    ) -> IMessenger:
        cache_key = self._cache_key(inbox_ref)

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

        self.logger.debug("Creating new messenger for %s", cache_key)

        if inbox_ref.platform is not PlatformType.WHATSAPP:
            raise ValueError(f"Unsupported platform: {inbox_ref.platform.value}")

        resolved = credentials
        if resolved is None:
            if self._credential_resolver is None:
                raise RuntimeError(
                    "MessengerFactory has no credential resolver and received no "
                    f"credentials for {inbox_ref}"
                )
            # Typed directory failures propagate unchanged.
            resolved = await self._credential_resolver.resolve_credentials(inbox_ref)
        if resolved.inbox_ref != inbox_ref:
            raise ValueError(
                f"credentials for {resolved.inbox_ref} cannot build a Messenger "
                f"for {inbox_ref}"
            )

        try:
            messenger = self._create_whatsapp_messenger(resolved)
        except InboxDirectoryError:
            raise
        except Exception as e:
            self.logger.error("Failed to create messenger for %s: %s", cache_key, e)
            raise RuntimeError(f"Messenger creation failed: {e}") from e

        self._messenger_cache[cache_key] = messenger
        return messenger

    def _create_whatsapp_messenger(
        self, credentials: ResolvedInboxCredentials
    ) -> WhatsAppMessenger:
        inbox_id = credentials.inbox_id
        session = self._get_session()
        client = WhatsAppClient(
            session=session,
            access_token=credentials.access_token.get_secret_value(),
            phone_number_id=inbox_id,
            logger=self.logger,
        )
        messenger = WhatsAppMessenger(
            client=client,
            media_handler=WhatsAppMediaHandler(
                client=client,
                inbox_id=inbox_id,
                media_download_client=self._get_media_download_client(),
            ),
            interactive_handler=WhatsAppInteractiveHandler(
                client=client, inbox_id=inbox_id
            ),
            template_handler=WhatsAppTemplateHandler(client=client, inbox_id=inbox_id),
            specialized_handler=WhatsAppSpecializedHandler(
                client=client, inbox_id=inbox_id
            ),
            inbox_id=inbox_id,
        )
        self.logger.info("✅ WhatsApp messenger created for inbox: %s", inbox_id)
        return messenger

    def get_supported_platforms(self) -> list[PlatformType]:
        return [PlatformType.WHATSAPP]

    def is_platform_supported(self, platform: PlatformType) -> bool:
        return platform in self.get_supported_platforms()

    def evict(self, inbox_ref: InboxRef) -> None:
        """Drop the cached Messenger for one Inbox (after rotation or deactivation)."""
        if self._messenger_cache.pop(self._cache_key(inbox_ref), None) is not None:
            self.logger.debug("Evicted cached messenger for %s", inbox_ref)

    def clear_cache(self, inbox_ref: InboxRef | None = None) -> None:
        if inbox_ref is not None:
            self.evict(inbox_ref)
            return
        self._messenger_cache.clear()
        self.logger.debug("Cleared entire messenger cache")
