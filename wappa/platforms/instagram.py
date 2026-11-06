"""Instagram's Platform entry: the one place that wires its inbound and outbound adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.instagram.processor import InstagramWebhookProcessor

from .entry import MessengerDeps, PlatformEntry

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.domain.inbox.ports import ResolvedInboxCredentials
    from wappa.domain.interfaces.messaging_interface import IMessenger

PLATFORM = PlatformType.INSTAGRAM
BUILTIN_FIELDS: frozenset[str] = InstagramWebhookProcessor.builtin_fields


def build_messenger(
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


def build_platform_messenger(messenger: IMessenger) -> IMessenger:
    from wappa.messaging.instagram.platform_messenger import InstagramMessenger

    return InstagramMessenger(messenger)


def entry(field_registry: FieldHandlerRegistry) -> PlatformEntry:
    return PlatformEntry(
        webhooks=InstagramWebhookProcessor(field_registry),
        build_messenger=build_messenger,
        display_name="Instagram",
        build_platform_messenger=build_platform_messenger,
    )
