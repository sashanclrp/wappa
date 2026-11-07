"""WhatsApp's Platform entry: the one place that wires its inbound and outbound adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.whatsapp.processor import WhatsAppWebhookProcessor

from .entry import MessengerDeps, PlatformEntry

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.domain.inbox.ports import ResolvedInboxCredentials
    from wappa.domain.interfaces.messaging_interface import IMessenger

PLATFORM = PlatformType.WHATSAPP
BUILTIN_FIELDS: frozenset[str] = WhatsAppWebhookProcessor.builtin_fields


def build_messenger(
    credentials: ResolvedInboxCredentials, deps: MessengerDeps
) -> IMessenger:
    from wappa.core.logging.logger import get_logger
    from wappa.messaging.whatsapp.client import WhatsAppClient
    from wappa.messaging.whatsapp.media.transport import WhatsAppMediaTransport
    from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter

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
        media_transport=WhatsAppMediaTransport(
            client=client,
            inbox_id=inbox_id,
            media_download_client=deps.media_download_client_provider(),
        ),
        inbox_id=inbox_id,
    )


def build_platform_messenger(messenger: IMessenger) -> IMessenger:
    from wappa.messaging.whatsapp.platform_messenger import WhatsAppMessenger

    return WhatsAppMessenger(messenger)


def entry(field_registry: FieldHandlerRegistry) -> PlatformEntry:
    from wappa.messaging.whatsapp.messenger import WhatsAppMessengerAdapter

    return PlatformEntry(
        webhooks=WhatsAppWebhookProcessor(field_registry),
        build_messenger=build_messenger,
        messenger_operations=WhatsAppMessengerAdapter.OPERATIONS,
        messenger_capabilities=WhatsAppMessengerAdapter.CAPABILITY_TYPES,
        display_name="WhatsApp",
        build_platform_messenger=build_platform_messenger,
    )
