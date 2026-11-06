"""Statuses lane: message statuses -> ``StatusWebhook``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.schema_drift import report_schema_drift, report_unmodelled
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        InboxBase,
        StatusWebhook,
        SystemWebhook,
    )
    from wappa.webhooks.whatsapp.models.status import WhatsAppMessageStatus
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _StatusesMixin(_ProcessorBase):
    """Statuses lane: message statuses -> ``StatusWebhook``."""

    def _create_status_from_data(
        self, status_data: dict[str, Any]
    ) -> WhatsAppMessageStatus:
        try:
            from wappa.webhooks.whatsapp.models.status import WhatsAppMessageStatus

            status = WhatsAppMessageStatus.model_validate(status_data)
            report_schema_drift(status, platform="whatsapp", logger=self.logger)
            return status

        except ValidationError as e:
            self.logger.error("Failed to parse WhatsApp message status: %s", e)
            raise

    async def _create_status_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase, **kwargs: Any
    ) -> StatusWebhook | SystemWebhook:
        from wappa.webhooks.core.webhook_interfaces import StatusWebhook
        from wappa.webhooks.whatsapp.models.status import KNOWN_WHATSAPP_STATUSES

        raw_statuses = webhook.get_raw_statuses()
        if not raw_statuses:
            raise ProcessorError(
                "No statuses found in status webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        # Parse the first status
        raw_status = raw_statuses[0]
        if raw_status.get("status") not in KNOWN_WHATSAPP_STATUSES:
            # A status value Meta added later: 200 + drift report, never a 400
            # that Meta retries and drops (ADR-0023).
            return self._create_unmodelled_status_webhook(
                webhook, inbox_base, raw_status
            )
        status = self._create_status_from_data(raw_status)

        # Extract conversation and error context
        conversation = self._extract_conversation_context(status)
        errors = self._extract_status_errors(status)

        recipient_phone_id = getattr(status, "wa_recipient_id", "")
        recipient_bsuid = getattr(status, "recipient_bsuid", None)
        recipient_parent_bsuid = getattr(status, "recipient_parent_bsuid", None)
        # Default canonical user_id to BSUID when available, else phone. The
        # webhook controller performs a best-effort phone → BSUID lookup when
        # BSUID is absent and persistence is configured.
        participant_phone_id = getattr(status, "recipient_participant_id", None)
        participant_bsuid = getattr(status, "recipient_participant_bsuid", None)
        bsuid_clean = recipient_bsuid.strip() if recipient_bsuid else ""
        if getattr(status, "recipient_type", None) == "group":
            canonical_user_id = participant_bsuid or participant_phone_id or None
            contact_identity = canonical_user_id or recipient_phone_id or ""
        else:
            canonical_user_id = bsuid_clean or recipient_phone_id or None
            contact_identity = status.recipient_id

        return StatusWebhook(
            inbox=inbox_base,
            message_id=getattr(status, "message_id", ""),
            status=status.status,
            recipient_phone_id=recipient_phone_id,
            recipient_bsuid=recipient_bsuid,
            recipient_parent_bsuid=recipient_parent_bsuid,
            user=self._create_status_user_from_contacts(webhook, contact_identity),
            recipient_type=getattr(status, "recipient_type", None),
            recipient_participant_phone_id=getattr(
                status, "recipient_participant_id", None
            ),
            recipient_participant_bsuid=getattr(
                status, "recipient_participant_bsuid", None
            ),
            recipient_participant_parent_bsuid=getattr(
                status, "recipient_participant_parent_bsuid", None
            ),
            user_id=canonical_user_id,
            timestamp=datetime.fromtimestamp(getattr(status, "timestamp", 0)),
            conversation=conversation,
            errors=errors,
            business_opaque_data=getattr(status, "business_opaque_data", None),
            recipient_identity_hash=getattr(status, "recipient_identity_hash", None),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    def _create_unmodelled_status_webhook(
        self,
        webhook: WhatsAppWebhook,
        inbox_base: InboxBase,
        raw_status: dict[str, Any],
    ) -> SystemWebhook:
        from wappa.webhooks.core.webhook_interfaces import (
            SystemEventDetail,
            SystemEventType,
            SystemWebhook,
        )

        value = raw_status.get("status")
        report_unmodelled(
            [f"WhatsAppMessageStatus.status={value}"],
            platform="whatsapp",
            logger=self.logger,
        )
        return SystemWebhook(
            inbox=inbox_base,
            system_event_type=SystemEventType.UNSUPPORTED_EVENT,
            event_detail=SystemEventDetail(
                platform_event={"field": "messages", "status": raw_status},
                detail=f"WhatsApp message status '{value}' is not modelled",
            ),
            user=None,
            timestamp=datetime.now(tz=UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
