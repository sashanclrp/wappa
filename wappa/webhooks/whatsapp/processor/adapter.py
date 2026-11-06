"""WhatsApp ``PlatformWebhooks`` adapter: composition, routing and ``translate``."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import ValidationError

from wappa.core.inbound.errors import ProcessorError
from wappa.core.inbound.platform_webhooks import RoutedWebhookDelivery
from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.whatsapp.fields import BUILTIN_WEBHOOK_FIELDS
from wappa.webhooks.whatsapp.processor.calls import _CallsMixin
from wappa.webhooks.whatsapp.processor.context import _ContextMixin
from wappa.webhooks.whatsapp.processor.custom import _CustomMixin
from wappa.webhooks.whatsapp.processor.errors import _ErrorsMixin
from wappa.webhooks.whatsapp.processor.history import _HistoryMixin
from wappa.webhooks.whatsapp.processor.message_factory import _MessageFactoryMixin
from wappa.webhooks.whatsapp.processor.message_updates import _MessageUpdatesMixin
from wappa.webhooks.whatsapp.processor.messages import _MessagesMixin
from wappa.webhooks.whatsapp.processor.statuses import _StatusesMixin
from wappa.webhooks.whatsapp.processor.system import _SystemMixin
from wappa.webhooks.whatsapp.routing import route_whatsapp_payload

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.domain.inbox.ports import IInboxCredentialResolver
    from wappa.webhooks.core.webhook_interfaces import InboxBase, UniversalWebhook
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook


class WhatsAppWebhookProcessor(
    _MessageFactoryMixin,
    _MessagesMixin,
    _MessageUpdatesMixin,
    _HistoryMixin,
    _CallsMixin,
    _StatusesMixin,
    _ErrorsMixin,
    _CustomMixin,
    _SystemMixin,
    _ContextMixin,
):
    """WhatsApp ``PlatformWebhooks`` adapter: Meta batch routing and translation."""

    builtin_fields: ClassVar[frozenset[str]] = BUILTIN_WEBHOOK_FIELDS

    def __init__(self, field_registry: FieldHandlerRegistry | None = None) -> None:
        self.logger = get_logger(__name__)
        # ``None`` means the Host registered no extension fields.
        self._field_registry = field_registry
        self._message_type_handlers: dict[str, Callable[..., BaseMessage]] = {
            "text": self._create_text_message,
            "interactive": self._create_interactive_message,
            "image": self._create_image_message,
            "audio": self._create_audio_message,
            "video": self._create_video_message,
            "document": self._create_document_message,
            "contact": self._create_contact_message,
            "location": self._create_location_message,
            "sticker": self._create_sticker_message,
            "system": self._create_system_message,
            "unsupported": self._create_unsupported_message,
            "reaction": self._create_reaction_message,
            "button": self._create_button_message,
            "order": self._create_order_message,
            "edit": self._create_lifecycle_message,
            "revoke": self._create_lifecycle_message,
        }

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    async def route(
        self, payload: dict[str, Any], resolver: IInboxCredentialResolver
    ) -> tuple[RoutedWebhookDelivery, ...]:
        return await route_whatsapp_payload(payload, resolver)

    def _is_registered_field(self, field: str | None) -> bool:
        return (
            field is not None
            and self._field_registry is not None
            and self._field_registry.get(field, PlatformType.WHATSAPP) is not None
        )

    def _parse_webhook_container(self, payload: dict[str, Any]) -> WhatsAppWebhook:
        try:
            from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook

            webhook = WhatsAppWebhook.model_validate(payload)
            report_schema_drift(webhook, platform="whatsapp", logger=self.logger)
            self.logger.debug(
                "Successfully parsed WhatsApp webhook from %s", webhook.business_id
            )
            return webhook

        except ValidationError as e:
            error_msg = f"Failed to parse WhatsApp webhook structure: {e}"
            self.logger.error(error_msg)
            raise ValueError(error_msg) from e

    async def translate(
        self,
        payload: dict[str, Any],
        *,
        inbox_id: str,
    ) -> UniversalWebhook:
        """Translate one routed change.

        The Inbox is ``value.metadata.phone_number_id`` when the change has
        metadata; a registered custom field has none and takes ``inbox_id``
        (the routed Inbox). The runtime checks the result against it.
        """
        try:
            webhook = self._parse_webhook_container(payload)
            self.logger.debug("Raw WhatsApp webhook received: %s", payload)

            inbox_base = self._create_inbox_base(webhook, inbox_id)
            universal_webhook: UniversalWebhook | None

            # System events are checked BEFORE incoming messages because system
            # messages (type=="system") arrive in the messages field.
            from wappa.webhooks.whatsapp.models.coexistence import (
                HistoryWebhookValue,
                SmbMessageEchoesWebhookValue,
            )

            coexistence = webhook.get_coexistence_event()
            changes = webhook.entry[0].changes if webhook.entry else []
            field = changes[0].field if changes else None
            if isinstance(coexistence, SmbMessageEchoesWebhookValue):
                universal_webhook = self._create_echo_webhook(
                    webhook, coexistence, inbox_base
                )
            elif isinstance(coexistence, HistoryWebhookValue):
                universal_webhook = self._create_history_webhook(
                    webhook, coexistence, inbox_base
                )
            elif field in ("account_offboarded", "account_reconnected"):
                universal_webhook = self._create_connection_webhook(
                    webhook, field, inbox_base
                )
            elif webhook.is_system_event:
                universal_webhook = await self._create_system_webhook(
                    webhook, inbox_base
                )
            elif webhook.is_call_event:
                universal_webhook = await self._create_call_webhook(webhook, inbox_base)
            elif webhook.is_incoming_message:
                universal_webhook = await self._create_incoming_message_webhook(
                    webhook, inbox_base
                )
            elif webhook.is_status_update:
                universal_webhook = await self._create_status_webhook(
                    webhook, inbox_base
                )
            elif webhook.has_errors:
                universal_webhook = await self._create_error_webhook(
                    webhook, inbox_base
                )
            elif webhook.is_custom_field and self._is_registered_field(field):
                universal_webhook = await self._create_custom_webhook(
                    webhook, inbox_base, payload
                )
            elif webhook.is_custom_field:
                universal_webhook = self._create_unmodelled_field_webhook(
                    webhook, inbox_base
                )
            else:
                universal_webhook = None

            if universal_webhook is None:
                # Unknown webhook type -- wrap as an ErrorWebhook
                from wappa.webhooks.core.webhook_interfaces import (
                    ErrorDetailBase,
                    ErrorWebhook,
                )

                error_detail = ErrorDetailBase(
                    error_code=400,
                    error_title="Unknown webhook type",
                    error_message="Webhook contains no recognizable content (messages, statuses, errors, or system events)",
                    error_type="webhook_format",
                    occurred_at=datetime.now(UTC),
                )

                return ErrorWebhook(
                    inbox=inbox_base,
                    errors=[error_detail],
                    timestamp=datetime.now(UTC),
                    error_level="webhook",
                    platform=PlatformType.WHATSAPP,
                    webhook_id=webhook.get_webhook_id(),
                )

            universal_webhook.set_raw_webhook_data(payload)

            return universal_webhook

        except Exception as e:
            self.logger.error(
                "Failed to create universal webhook: %s", e, exc_info=True
            )
            raise ProcessorError(
                f"Failed to transform WhatsApp webhook to universal interface: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            ) from e

    def _create_inbox_base(self, webhook: WhatsAppWebhook, inbox_id: str) -> InboxBase:
        from wappa.webhooks.core.webhook_interfaces import InboxBase

        # Built-in field payloads carry value.metadata with phone number info.
        # Custom registered fields (e.g. message_template_status_update) do
        # not. Payload routing has already resolved WABA scope and supplies the
        # per-delivery inbox_id.
        first_value = webhook.entry[0].changes[0].value
        metadata = getattr(first_value, "metadata", None)
        waba_id = webhook.entry[0].id
        if metadata is not None:
            return InboxBase(
                inbox_id=metadata.phone_number_id,
                display_address=metadata.display_phone_number,
                platform_account_id=waba_id,
            )

        return InboxBase(
            inbox_id=inbox_id,
            display_address="",
            platform_account_id=waba_id,
        )
