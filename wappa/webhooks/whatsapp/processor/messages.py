"""Incoming message lane: ``messages`` -> ``InboundMessageWebhook``."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, MessageType, PlatformType
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        InboundMessageWebhook,
        InboxBase,
        MessageUpdateWebhook,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _MessagesMixin(_ProcessorBase):
    """Incoming message lane: ``messages`` -> ``InboundMessageWebhook``."""

    async def _create_incoming_message_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase, **kwargs: Any
    ) -> InboundMessageWebhook | MessageUpdateWebhook:
        from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook

        raw_messages = webhook.get_raw_messages()
        if not raw_messages:
            raise ProcessorError(
                "No messages found in incoming message webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        raw_message = raw_messages[0]
        raw_message_type = raw_message.get("type", "text")

        # WhatsApp uses 'contacts' but the enum uses 'contact'.
        whatsapp_to_universal_type = {"contacts": "contact"}
        universal_message_type = whatsapp_to_universal_type.get(
            raw_message_type, raw_message_type
        )

        message_type = MessageType(universal_message_type)
        message = self._create_message_from_data(raw_message, message_type)
        message_type = message.message_type  # an unmodelled subtype becomes UNSUPPORTED
        if message_type in (MessageType.EDIT, MessageType.REVOKE):
            return self._create_message_update_webhook(webhook, message, inbox_base)

        # Create user base from contacts
        user_base = self._create_user_base_from_contacts(webhook, message.sender_id)

        # Extract WhatsApp-specific contexts
        business_context = self._extract_business_context(raw_message)
        forward_context = self._extract_forward_context(raw_message)
        entry_referral = self._extract_entry_referral(raw_message)

        return InboundMessageWebhook(
            inbox=inbox_base,
            user=user_base,
            message=message,
            business_context=business_context,
            forward_context=forward_context,
            entry_referral=entry_referral,
            timestamp=datetime.fromtimestamp(message.timestamp),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
