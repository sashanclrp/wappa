"""System families: ``business_username_updates`` and ``smb_app_state_sync``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.webhook_interfaces import SystemEventDetail, SystemEventType
from wappa.webhooks.whatsapp.processor.system.parts import SystemParts

if TYPE_CHECKING:
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


def build_business_username_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    username_event = webhook.get_business_username_event()
    if username_event is None:
        raise ProcessorError(
            "No business_username_updates value found in system webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )

    event_timestamp = datetime.now(UTC)
    system_event_type = SystemEventType.BUSINESS_USERNAME_UPDATE
    event_detail = SystemEventDetail(
        username=username_event.username,
        username_status=username_event.status,
        display_phone_number=username_event.display_phone_number,
    )
    entry_time = webhook.entry[0].time
    if entry_time is not None:
        event_timestamp = datetime.fromtimestamp(entry_time, tz=UTC)
    return SystemParts(system_event_type, event_detail, event_timestamp, None)


def build_app_state_sync_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook, field: str
) -> SystemParts:
    from wappa.webhooks.core.webhook_interfaces import ContactSync, UserBase
    from wappa.webhooks.whatsapp.models.coexistence import SmbAppStateSyncWebhookValue

    coexistence = webhook.get_coexistence_event()
    if not isinstance(coexistence, SmbAppStateSyncWebhookValue):
        raise ProcessorError(
            f"No typed {field} value found in system webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )
    state = coexistence.state_sync[0]
    contact = state.contact
    system_event_type = SystemEventType.SMB_APP_STATE_SYNC
    event_detail = SystemEventDetail(
        contact_sync=ContactSync(
            action=state.action,
            timestamp=int(state.metadata.timestamp),
            full_name=contact.full_name,
            first_name=contact.first_name,
            phone_number=contact.phone_number,
            user_id=contact.user_id,
            parent_user_id=contact.parent_user_id,
            username=contact.username,
        )
    )
    event_timestamp = datetime.fromtimestamp(int(state.metadata.timestamp), tz=UTC)
    user_base = UserBase(
        phone_number=contact.phone_number or "",
        bsuid=contact.user_id,
        parent_bsuid=contact.parent_user_id,
        username=contact.username,
        profile_name=contact.full_name,
    )
    return SystemParts(system_event_type, event_detail, event_timestamp, user_base)
