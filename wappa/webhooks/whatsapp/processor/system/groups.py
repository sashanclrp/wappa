"""System family: ``group_participants_update`` -> GROUP_PARTICIPANTS_UPDATE."""

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


def build_group_event(
    processor: _ProcessorBase, webhook: WhatsAppWebhook
) -> SystemParts:
    from wappa.webhooks.core.webhook_interfaces import (
        GroupParticipant,
        GroupUpdate,
        UserBase,
    )
    from wappa.webhooks.whatsapp.models.system import GroupParticipantsUpdateEntry

    user_base = None
    raw_group_updates = webhook.get_raw_group_updates()
    if not raw_group_updates:
        raise ProcessorError(
            "No groups found in group_participants_update webhook",
            ErrorCode.PROCESSING_ERROR,
            PlatformType.WHATSAPP,
        )

    group_update = GroupParticipantsUpdateEntry.model_validate(raw_group_updates[0])
    report_schema_drift(group_update, platform="whatsapp", logger=processor.logger)
    participant = None
    if group_update.added_participants:
        participant = group_update.added_participants[0]
    elif group_update.removed_participants:
        participant = group_update.removed_participants[0]

    wa_id = group_update.wa_id or (participant.wa_id if participant else None)
    user_id = group_update.user_id or (participant.user_id if participant else None)
    parent_user_id = group_update.parent_user_id or (
        participant.parent_user_id if participant else None
    )
    username = group_update.username or (participant.username if participant else None)

    system_event_type = SystemEventType.GROUP_PARTICIPANTS_UPDATE
    event_detail = SystemEventDetail(
        wa_id=wa_id,
        user_id=user_id,
        parent_user_id=parent_user_id,
        group_id=group_update.group_id,
        group_event_type=group_update.type,
        group_update=GroupUpdate(
            group_id=group_update.group_id,
            event_type=group_update.type,
            timestamp=group_update.timestamp,
            request_id=group_update.request_id,
            initiated_by=group_update.initiated_by,
            reason=group_update.reason,
            join_request_id=group_update.join_request_id,
            added=tuple(
                GroupParticipant(**p.model_dump())
                for p in group_update.added_participants or []
            ),
            removed=tuple(
                GroupParticipant(**p.model_dump())
                for p in group_update.removed_participants or []
            ),
        ),
    )
    event_timestamp = datetime.fromtimestamp(group_update.timestamp, tz=UTC)
    if wa_id or user_id:
        user_base = UserBase(
            phone_number=wa_id or "",
            bsuid=user_id,
            parent_bsuid=parent_user_id,
            username=username,
        )
    return SystemParts(system_event_type, event_detail, event_timestamp, user_base)
