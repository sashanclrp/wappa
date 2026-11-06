"""System family: ``user_preferences`` -> MARKETING_PREFERENCE."""

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


def build_preference_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    from wappa.webhooks.whatsapp.models.system import UserPreferenceEntry

    user_base = None
    raw_prefs = webhook.get_raw_user_preferences()
    if not raw_prefs:
        raise ProcessorError(
            "No user_preferences found in system webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )

    pref = UserPreferenceEntry.model_validate(raw_prefs[0])
    report_schema_drift(pref, platform="whatsapp", logger=processor.logger)

    system_event_type = SystemEventType.MARKETING_PREFERENCE
    event_detail = SystemEventDetail(
        wa_id=pref.wa_id,
        user_id=pref.user_id,
        parent_user_id=pref.parent_user_id,
        detail=pref.detail,
        category=pref.category,
        preference_value=pref.value,
    )
    event_timestamp = datetime.fromtimestamp(pref.timestamp, tz=UTC)

    if pref.wa_id or pref.user_id:
        sender_id = pref.user_id or pref.wa_id or ""
        user_base = processor._create_user_base_from_contacts(webhook, sender_id)
    return SystemParts(system_event_type, event_detail, event_timestamp, user_base)
