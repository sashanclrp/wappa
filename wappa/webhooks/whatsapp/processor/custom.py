"""Custom lane: registered extension fields and unmodelled Meta fields."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.schema_drift import report_unmodelled
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        CustomWebhook,
        InboxBase,
        SystemWebhook,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _CustomMixin(_ProcessorBase):
    """Custom lane: registered extension fields and unmodelled Meta fields."""

    def _create_unmodelled_field_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase
    ) -> SystemWebhook:
        """A Meta field Wappa does not model and no parser was registered for.

        Delivered as ``UNSUPPORTED_EVENT`` with the native value as evidence,
        exactly like Instagram's unknown change fields (ADR-0025), and logged
        as schema drift. Meta gets a 200, so it does not retry (ADR-0023).
        """
        from wappa.webhooks.core.webhook_interfaces import (
            SystemEventDetail,
            SystemEventType,
            SystemWebhook,
        )

        change = webhook.entry[0].changes[0]
        report_unmodelled(
            [f"webhook field '{change.field}'"], platform="whatsapp", logger=self.logger
        )
        return SystemWebhook(
            inbox=inbox_base,
            system_event_type=SystemEventType.UNSUPPORTED_EVENT,
            event_detail=SystemEventDetail(
                platform_event={
                    "field": change.field,
                    "value": change.value.model_dump(),
                },
                detail=f"WhatsApp webhook field '{change.field}' is not modelled",
            ),
            user=None,
            timestamp=datetime.now(tz=UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    async def _create_custom_webhook(
        self,
        webhook: WhatsAppWebhook,
        inbox_base: InboxBase,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> CustomWebhook:
        """Build a CustomWebhook for an app-registered Meta webhook field.

        Parser failures bubble up as ``ProcessorError`` — a registered field
        whose payload doesn't match the app's schema is a real error, not a
        silent drop.
        """
        from wappa.webhooks.core.webhook_interfaces import CustomWebhook

        change = webhook.entry[0].changes[0]
        field_name = change.field
        registry = self._field_registry
        if registry is None:
            raise ProcessorError(
                "No custom field registry is configured",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )
        handler_spec = registry.get(field_name, PlatformType.WHATSAPP)
        if handler_spec is None:
            raise ProcessorError(
                f"No registered handler for webhook field '{field_name}'",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        raw_value: dict[str, Any] = change.value.model_dump()

        try:
            parsed = handler_spec.parser(raw_value)
        except Exception as e:
            raise ProcessorError(
                f"Parser for field '{field_name}' failed: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            ) from e

        return CustomWebhook(
            inbox=inbox_base,
            field_name=field_name,
            parsed=parsed,
            raw_value=raw_value,
            timestamp=datetime.now(UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
