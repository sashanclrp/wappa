"""The Platform Registry's entry shape: what one installed Platform provides."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from wappa.core.inbound.platform_webhooks import PlatformWebhooks
    from wappa.domain.inbox.ports import ResolvedInboxCredentials
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry


@dataclass(frozen=True, slots=True)
class MessengerDeps:
    """Wappa-owned resources a Messenger builder draws on."""

    session_provider: Callable[[], httpx.AsyncClient]
    media_download_client_provider: Callable[[], httpx.AsyncClient]
    graph_api_version: str
    graph_base_url: str
    sent_registry: ISentMessageRegistry | None = None


MessengerBuilder = Callable[["ResolvedInboxCredentials", MessengerDeps], "IMessenger"]
PlatformMessengerBuilder = Callable[["IMessenger"], "IMessenger"]
"""Extend the dispatch's core Messenger (pipeline-wrapped) with Platform-only
capabilities. It never builds a second Messenger."""


@dataclass(frozen=True, slots=True)
class PlatformEntry:
    """One installed Platform.

    ``build_platform_messenger`` receives the core Messenger already built for
    a dispatch and returns that Platform's Platform Messenger, bound on the
    handler under the Platform's value (``self.whatsapp``, ``self.instagram``).
    ``None`` means the Platform has no Platform-only capabilities to add.
    """

    webhooks: PlatformWebhooks
    build_messenger: MessengerBuilder
    display_name: str
    build_platform_messenger: PlatformMessengerBuilder | None = None
    messenger_operations: frozenset[str] = frozenset(
        {"send_text", "resolve_platform_user_profile"}
    )
    messenger_capabilities: frozenset[type] = frozenset()
