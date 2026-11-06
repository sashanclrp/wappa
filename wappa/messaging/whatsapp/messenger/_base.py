"""Typed attributes every WhatsApp Messenger mixin relies on."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logging import Logger

    from wappa.core.logging.logger import ContextLogger
    from wappa.messaging.whatsapp.client import WhatsAppClient
    from wappa.messaging.whatsapp.media.transport import WhatsAppMediaTransport
    from wappa.messaging.whatsapp.payloads.media import WhatsAppMediaPayloadBuilder
    from wappa.messaging.whatsapp.payloads.text import WhatsAppMessagePayloadBuilder


class _WhatsAppMessengerBase:
    """Attributes the mixins read; ``WhatsAppMessengerAdapter.__init__`` sets them."""

    client: WhatsAppClient
    media_transport: WhatsAppMediaTransport
    logger: Logger | ContextLogger
    _inbox_id: str
    _message_payloads: WhatsAppMessagePayloadBuilder
    _media_payloads: WhatsAppMediaPayloadBuilder
