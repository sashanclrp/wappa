"""Error lane: ``errors`` -> ``ErrorWebhook``."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa.core.inbound.errors import ProcessorError
from wappa.domain.error_evidence import meta_error_evidence
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        ErrorWebhook,
        InboxBase,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _ErrorsMixin(_ProcessorBase):
    """Error lane: ``errors`` -> ``ErrorWebhook``."""

    async def _create_error_webhook(
        self, webhook: WhatsAppWebhook, inbox_base: InboxBase, **kwargs: Any
    ) -> ErrorWebhook:
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase, ErrorWebhook

        webhook_errors: list[dict[str, Any]] = []
        for entry in webhook.entry:
            for change in entry.changes:
                errors = getattr(change.value, "errors", None)
                if isinstance(errors, list):
                    webhook_errors.extend(errors)

        if not webhook_errors:
            raise ProcessorError(
                "Error webhook received without error entries",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        # Convert to ErrorDetailBase list
        error_details = []
        for error in webhook_errors:
            error_data = error.get("error_data")
            error_details_text = (
                error_data.get("details")
                if isinstance(error_data, dict)
                else error.get("details")
            )
            error_detail = ErrorDetailBase(
                error_code=int(error.get("code", 0)),
                error_evidence=meta_error_evidence(
                    f"{error.get('code', 0)}/{error['error_subcode']}"
                    if error.get("error_subcode") is not None
                    else error.get("code")
                ),
                error_title=str(error.get("title", "Unknown error")),
                error_message=str(error.get("message", "")),
                error_details=error_details_text,
                documentation_url=error.get("href"),
                error_type="whatsapp_api",
                occurred_at=datetime.now(UTC),
            )
            error_details.append(error_detail)

        return ErrorWebhook(
            inbox=inbox_base,
            errors=error_details,
            timestamp=datetime.now(UTC),
            error_level="system",
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
