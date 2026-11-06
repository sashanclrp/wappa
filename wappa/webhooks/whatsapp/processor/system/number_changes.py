"""System family: system messages in ``messages`` -> NUMBER_CHANGE or USER_ID_CHANGE."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.core.webhook_interfaces import SystemEventDetail, SystemEventType
from wappa.webhooks.whatsapp.processor.system.parts import SystemParts

if TYPE_CHECKING:
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


def build_system_message_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    # System messages from the messages field (type=="system")
    raw_messages = webhook.get_raw_messages()
    if not raw_messages:
        raise ProcessorError(
            "No system messages found in webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )

    message = processor._create_system_message(raw_messages[0])
    report_schema_drift(message, platform="whatsapp", logger=processor.logger)

    if message.is_number_change:
        system_event_type = SystemEventType.NUMBER_CHANGE
        old_phone, new_phone = message.extract_phone_numbers()
        event_detail = SystemEventDetail(
            wa_id=message.new_wa_id,
            body=message.system_message,
            old_phone_number=old_phone,
            new_phone_number=new_phone,
        )
    else:
        # user_changed_user_id
        system_event_type = SystemEventType.USER_ID_CHANGE
        event_detail = SystemEventDetail(
            wa_id=message.from_ or None,
            user_id=message.new_user_id,
            previous_user_id=message.previous_user_id,
            current_user_id=message.new_user_id,
            parent_user_id=message.system.parent_user_id,
            body=message.system_message,
        )

    event_timestamp = datetime.fromtimestamp(message.timestamp, tz=UTC)
    user_base = processor._create_user_base_from_contacts(webhook, message.sender_id)
    return SystemParts(system_event_type, event_detail, event_timestamp, user_base)
