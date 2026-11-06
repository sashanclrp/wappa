"""Factory for creating platform-specific IMessenger implementations."""

from __future__ import annotations

import weakref
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING

from wappa.core.config.settings import settings
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.errors import InboxDirectoryError
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry
from wappa.domain.interfaces.session_provider import HTTPSessionClosedError

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
        graph_api_version: str | None = None,
        graph_base_url: str | None = None,
        max_cached_messengers: int = 128,
        sent_registry: ISentMessageRegistry | None = None,
    ) -> None:
        self._session_provider = session_provider
        self._sent_registry = sent_registry
        self._credential_resolver = credential_resolver
        self._media_download_client_provider = media_download_client_provider
        self._graph_api_version = graph_api_version
        self._graph_base_url = graph_base_url
        if max_cached_messengers < 0:
            raise ValueError("max_cached_messengers must be >= 0")
        self._max_cached_messengers = max_cached_messengers
        self.logger = get_logger(__name__)
        self._messenger_cache: OrderedDict[str, IMessenger] = OrderedDict()
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
                self._messenger_cache.move_to_end(cache_key)
                self.logger.debug("Using cached messenger for %s", cache_key)
                return self._messenger_cache[cache_key]
            except HTTPSessionClosedError:
                self.logger.warning(
                    "Cached messenger for %s has stale session, evicting", cache_key
                )
                del self._messenger_cache[cache_key]

        self.logger.debug("Creating new messenger for %s", cache_key)

        # Imported here: the Platform Registry imports the inbound adapters,
        # whose package imports the runtime that builds this factory.
        from wappa.platforms import PLATFORMS, MessengerDeps

        entry = PLATFORMS.get(inbox_ref.platform)
        if entry is None:
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

        deps = MessengerDeps(
            session_provider=self._session_provider,
            media_download_client_provider=self._media_download_client_provider,
            # Without a Meta Application Configuration, its env defaults apply.
            graph_api_version=self._graph_api_version or settings.api_version,
            graph_base_url=self._graph_base_url or settings.base_url,
            sent_registry=self._sent_registry,
        )
        try:
            messenger = entry.build_messenger(resolved, deps)
        except InboxDirectoryError:
            raise
        except Exception as e:
            self.logger.error("Failed to create messenger for %s: %s", cache_key, e)
            raise RuntimeError(f"Messenger creation failed: {e}") from e

        if self._max_cached_messengers:
            self._messenger_cache[cache_key] = messenger
            self._messenger_cache.move_to_end(cache_key)
            while len(self._messenger_cache) > self._max_cached_messengers:
                evicted_key, _ = self._messenger_cache.popitem(last=False)
                self.logger.debug(
                    "Evicted least-recently-used messenger for %s", evicted_key
                )
        return messenger

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
