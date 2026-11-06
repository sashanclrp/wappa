"""Calls lane: ``calls`` -> ``CallWebhook``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        CallWebhook,
        InboxBase,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _CallsMixin(_ProcessorBase):
    """Calls lane: ``calls`` -> ``CallWebhook``."""

    async def _create_call_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase, **kwargs: Any
    ) -> CallWebhook:
        from wappa.webhooks.core.webhook_interfaces import CallWebhook

        value = webhook.get_call_event()
        if value is None:
            raise ProcessorError(
                "No calls value found in calls webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        event: str
        if value.calls:
            call = value.calls[0]
            if call.direction == "USER_INITIATED":
                phone_number = call.from_
                bsuid = call.from_user_id
                parent_bsuid = call.from_parent_user_id
            else:
                phone_number = call.to
                bsuid = call.to_user_id
                parent_bsuid = call.to_parent_user_id
            event = call.event
            direction = call.direction
            status = call.status
            duration = call.duration
            business_opaque_data = call.biz_opaque_callback_data
            session = call.session.model_dump() if call.session else None
            raw_call = call.model_dump(by_alias=True)
            call_id = call.id
            timestamp = call.timestamp
        elif value.statuses:
            call_status = value.statuses[0]
            phone_number = call_status.recipient_id
            bsuid = call_status.recipient_user_id
            parent_bsuid = call_status.recipient_parent_user_id
            event = "status"
            direction = "BUSINESS_INITIATED"
            status = call_status.status
            duration = None
            business_opaque_data = call_status.biz_opaque_callback_data
            session = None
            raw_call = call_status.model_dump()
            call_id = call_status.id
            timestamp = call_status.timestamp
        else:
            raise ProcessorError(
                "Calls webhook contains neither calls nor statuses",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        canonical_user_id = bsuid or phone_number or ""
        user = self._create_user_base_from_contacts(webhook, canonical_user_id)
        user.parent_bsuid = parent_bsuid or user.parent_bsuid

        return CallWebhook(
            inbox=inbox_base,
            user=user if user.user_id else None,
            call_id=call_id,
            event=event,
            direction=direction,
            timestamp=datetime.fromtimestamp(int(timestamp), tz=UTC),
            status=status,
            duration=duration,
            phone_number=phone_number,
            bsuid=bsuid,
            parent_bsuid=parent_bsuid,
            business_opaque_data=business_opaque_data,
            session=session,
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
            raw_call=raw_call,
        )
