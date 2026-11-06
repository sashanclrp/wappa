"""System family: ``user_id_update`` -> USER_ID_CHANGE."""

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


def build_user_id_update_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    from wappa.webhooks.whatsapp.models.system import UserIdUpdateEntry

    user_base = None
    raw_updates = webhook.get_raw_user_id_updates()
    if not raw_updates:
        raise ProcessorError(
            "No user_id_update found in system webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )

    update = UserIdUpdateEntry.model_validate(raw_updates[0])
    report_schema_drift(update, platform="whatsapp", logger=processor.logger)
    parent = update.parent_user_id

    system_event_type = SystemEventType.USER_ID_CHANGE
    event_detail = SystemEventDetail(
        wa_id=update.wa_id,
        detail=update.detail,
        previous_user_id=update.user_id.previous,
        current_user_id=update.user_id.current,
        previous_parent_user_id=parent.previous if parent else None,
        current_parent_user_id=parent.current if parent else None,
    )
    event_timestamp = datetime.fromtimestamp(int(update.timestamp), tz=UTC)

    if update.wa_id:
        user_base = processor._create_user_base_from_contacts(webhook, update.wa_id)
    return SystemParts(system_event_type, event_detail, event_timestamp, user_base)
