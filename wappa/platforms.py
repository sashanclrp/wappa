"""Platform Registry: the composition root for installed Platforms.

``PLATFORMS.keys()`` is the one installed-Platform set. Each ``PlatformEntry``
names the Platform's inbound ``PlatformWebhooks`` adapter, its Messenger
builder, its display name and, optionally, its Platform Messenger builder (the
Host-facing ``self.whatsapp`` / ``self.instagram`` on the handler). ``PlatformType`` is vocabulary: a member with no
entry (Telegram, Teams) is reserved, not installed, and every lookup of a
missing key fails loudly instead of falling through to another Platform.

Platform-specific imports and branches are legitimate only here and in the
adapter folders. A new Platform adds its adapters, one ``PlatformEntry`` in
``build_platforms`` and its ``builtin_fields`` in ``BUILTIN_FIELDS``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from wappa.core.events.field_registry import FieldHandlerRegistry
from wappa.processors.instagram_processor import InstagramWebhookProcessor
from wappa.processors.whatsapp_processor import WhatsAppWebhookProcessor
from wappa.schemas.core.types import PlatformType

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


def _build_whatsapp_messenger(
    credentials: ResolvedInboxCredentials, deps: MessengerDeps
) -> IMessenger:
    from wappa.core.logging.logger import get_logger
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
    from wappa.messaging.whatsapp.messenger.whatsapp_messenger import (
        WhatsAppMessengerAdapter,
    )

    inbox_id = credentials.inbox_id
    client = WhatsAppClient(
        session=deps.session_provider(),
        access_token=credentials.access_token.get_secret_value(),
        phone_number_id=inbox_id,
        logger=get_logger(__name__),
        api_version=deps.graph_api_version,
        base_url=deps.graph_base_url,
    )
    return WhatsAppMessengerAdapter(
        client=client,
        media_handler=WhatsAppMediaHandler(
            client=client,
            inbox_id=inbox_id,
            media_download_client=deps.media_download_client_provider(),
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


def _build_instagram_messenger(
    credentials: ResolvedInboxCredentials, deps: MessengerDeps
) -> IMessenger:
    from wappa.messaging.instagram.messenger import InstagramMessengerAdapter

    return InstagramMessengerAdapter(
        inbox_ref=credentials.inbox_ref,
        access_token=credentials.access_token,
        session_provider=deps.session_provider,
        graph_api_version=deps.graph_api_version,
        graph_base_url=deps.graph_base_url,
        media_download_client_provider=deps.media_download_client_provider,
        sent_registry=deps.sent_registry,
    )


def _build_whatsapp_platform_messenger(messenger: IMessenger) -> IMessenger:
    from wappa.messaging.whatsapp.platform_messenger import WhatsAppMessenger

    return WhatsAppMessenger(messenger)


def _build_instagram_platform_messenger(messenger: IMessenger) -> IMessenger:
    from wappa.messaging.instagram.platform_messenger import InstagramMessenger

    return InstagramMessenger(messenger)


BUILTIN_FIELDS: Mapping[PlatformType, frozenset[str]] = MappingProxyType(
    {
        PlatformType.WHATSAPP: WhatsAppWebhookProcessor.builtin_fields,
        PlatformType.INSTAGRAM: InstagramWebhookProcessor.builtin_fields,
    }
)
"""Each installed Platform's reserved webhook fields; seeds ``FieldHandlerRegistry``."""


def build_platforms(
    field_registry: FieldHandlerRegistry,
) -> Mapping[PlatformType, PlatformEntry]:
    """Build the installed-Platform table bound to one app's field registry."""
    return MappingProxyType(
        {
            PlatformType.WHATSAPP: PlatformEntry(
                webhooks=WhatsAppWebhookProcessor(field_registry),
                build_messenger=_build_whatsapp_messenger,
                display_name="WhatsApp",
                build_platform_messenger=_build_whatsapp_platform_messenger,
            ),
            PlatformType.INSTAGRAM: PlatformEntry(
                webhooks=InstagramWebhookProcessor(field_registry),
                build_messenger=_build_instagram_messenger,
                display_name="Instagram",
                build_platform_messenger=_build_instagram_platform_messenger,
            ),
        }
    )


PLATFORMS: Mapping[PlatformType, PlatformEntry] = build_platforms(
    FieldHandlerRegistry(BUILTIN_FIELDS)
)
"""The installed Platforms with no Host extension fields.

Each built app holds its own table, ``build_platforms(builder.field_registry)``,
on ``app.state.platforms``; the keys are always the same installed set.
"""


def platform_messenger(
    messenger: IMessenger,
    platforms: Mapping[PlatformType, PlatformEntry] | None = None,
) -> IMessenger | None:
    """The Platform Messenger for ``messenger``'s Platform, or ``None``.

    Looks the Platform up in ``platforms`` (the app's table; ``PLATFORMS``
    when omitted) and lets its entry extend the given Messenger. ``None`` when
    the Platform is not in the table or adds no Platform Messenger.
    """
    entry = (platforms if platforms is not None else PLATFORMS).get(messenger.platform)
    if entry is None or entry.build_platform_messenger is None:
        return None
    return entry.build_platform_messenger(messenger)


__all__ = [
    "BUILTIN_FIELDS",
    "PLATFORMS",
    "MessengerBuilder",
    "MessengerDeps",
    "PlatformEntry",
    "PlatformMessengerBuilder",
    "build_platforms",
    "platform_messenger",
]
