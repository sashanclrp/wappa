import hashlib
import hmac
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from wappa.core.config.settings import settings
from wappa.processors.base_processor import (
    BaseWebhookProcessor,
    ProcessorCapabilities,
    ProcessorError,
)
from wappa.schemas.core.recipient import looks_like_bsuid, looks_like_phone_number
from wappa.schemas.core.types import ErrorCode, MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.base_status import BaseMessageStatus
from wappa.webhooks.core.base_webhook import BaseWebhook

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.webhooks.core.webhook_interfaces import (
        AdReferralBase,
        BusinessContextBase,
        CallWebhook,
        ConversationBase,
        CustomWebhook,
        ErrorDetailBase,
        ErrorWebhook,
        ForwardContextBase,
        InboundMessageWebhook,
        InboxBase,
        StatusWebhook,
        SystemWebhook,
        UniversalWebhook,
        UserBase,
        WhatsAppIncomingWebhookData,
    )


class WhatsAppWebhookProcessor(BaseWebhookProcessor):
    """WhatsApp Business Platform webhook processor."""

    def __init__(self):
        super().__init__()

        self._field_registry: FieldHandlerRegistry | None = None

        # Define WhatsApp-specific capabilities
        self._capabilities = ProcessorCapabilities(
            platform=PlatformType.WHATSAPP,
            supported_message_types={
                MessageType.TEXT,
                MessageType.INTERACTIVE,
                MessageType.IMAGE,
                MessageType.AUDIO,
                MessageType.VIDEO,
                MessageType.DOCUMENT,
                MessageType.CONTACT,
                MessageType.LOCATION,
                MessageType.STICKER,
                MessageType.REACTION,
                MessageType.SYSTEM,
                MessageType.EDIT,
                MessageType.REVOKE,
                # WhatsApp-specific types mapped to closest standard types
                MessageType("button"),  # Interactive button responses
                MessageType("order"),  # Product orders
                MessageType("unsupported"),  # Unsupported message types
            },
            supports_status_updates=True,
            supports_signature_validation=True,
            supports_error_webhooks=True,
            max_payload_size=1024 * 1024,  # 1MB typical WhatsApp webhook limit
            rate_limit_per_minute=1000,  # WhatsApp API rate limits
        )

        # Register message type handlers
        self._register_message_handlers()

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def capabilities(self) -> ProcessorCapabilities:
        return self._capabilities

    def set_field_registry(self, registry: "FieldHandlerRegistry | None") -> None:
        """Attach (or clear) the app-supplied custom webhook field registry."""
        self._field_registry = registry

    def _log_contract_drift(self, error: ValidationError) -> None:
        """Emit a stable, page-worthy signal for strict Meta schema drift."""
        extra_fields = [
            ".".join(str(part) for part in item["loc"])
            for item in error.errors(include_input=False)
            if item["type"] == "extra_forbidden"
        ]
        if extra_fields:
            self.logger.critical(
                "WHATSAPP_WEBHOOK_CONTRACT_DRIFT error_type=extra_forbidden fields=%s",
                ",".join(extra_fields),
            )

    def _register_message_handlers(self) -> None:
        self.register_message_handler("text", self._create_text_message)
        self.register_message_handler("interactive", self._create_interactive_message)
        self.register_message_handler("image", self._create_image_message)
        self.register_message_handler("audio", self._create_audio_message)
        self.register_message_handler("video", self._create_video_message)
        self.register_message_handler("document", self._create_document_message)
        self.register_message_handler("contact", self._create_contact_message)
        self.register_message_handler("location", self._create_location_message)
        self.register_message_handler("sticker", self._create_sticker_message)
        self.register_message_handler("system", self._create_system_message)
        self.register_message_handler("unsupported", self._create_unsupported_message)
        self.register_message_handler("reaction", self._create_reaction_message)
        self.register_message_handler("button", self._create_button_message)
        self.register_message_handler("order", self._create_order_message)
        self.register_message_handler("edit", self._create_lifecycle_message)
        self.register_message_handler("revoke", self._create_lifecycle_message)

    def validate_webhook_signature(
        self, payload: bytes, signature: str, **kwargs
    ) -> bool:
        if not settings.wp_webhook_verify_token:
            self.logger.warning(
                "WhatsApp webhook verification token not configured - skipping signature validation"
            )
            return True

        try:
            if not signature.startswith("sha256="):
                self.logger.error(
                    "Invalid signature format - must start with 'sha256='"
                )
                return False

            provided_hash = signature.removeprefix("sha256=")
            expected_hash = hmac.new(
                settings.wp_webhook_verify_token.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()

            is_valid = hmac.compare_digest(expected_hash, provided_hash)
            if not is_valid:
                self.logger.error("Webhook signature validation failed")
            return is_valid

        except Exception as e:
            self.logger.error(
                "Error validating webhook signature: %s", e, exc_info=True
            )
            return False

    def parse_webhook_container(self, payload: dict[str, Any], **kwargs) -> BaseWebhook:
        try:
            from wappa.webhooks.whatsapp.webhook_container import WhatsAppWebhook

            # A missing registry means no custom fields are registered — only
            # built-ins are accepted, preserving backwards-compatible 400s.
            context = {"field_registry": self._field_registry}
            webhook = WhatsAppWebhook.model_validate(payload, context=context)
            self.logger.debug(
                "Successfully parsed WhatsApp webhook from %s", webhook.business_id
            )
            return webhook

        except ValidationError as e:
            self._log_contract_drift(e)
            error_msg = f"Failed to parse WhatsApp webhook structure: {e}"
            self.logger.error(error_msg)
            raise ValueError(error_msg) from e

    def get_supported_message_types(self) -> set[MessageType]:
        return self._capabilities.supported_message_types

    def create_message_from_data(
        self, message_data: dict[str, Any], message_type: MessageType, **kwargs
    ) -> BaseMessage:
        message_type_str = message_type.value
        handler = self.get_message_handler(message_type_str)
        if handler is None:
            from .base_processor import UnsupportedMessageTypeError

            raise UnsupportedMessageTypeError(message_type_str, self.platform)

        return handler(message_data, **kwargs)

    def create_status_from_data(
        self, status_data: dict[str, Any], **kwargs
    ) -> BaseMessageStatus:
        try:
            from wappa.webhooks.whatsapp.status_models import WhatsAppMessageStatus

            return WhatsAppMessageStatus.model_validate(status_data)

        except ValidationError as e:
            self.logger.error("Failed to parse WhatsApp message status: %s", e)
            raise

    # Message creation handlers

    def _create_text_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.text import WhatsAppTextMessage

        return WhatsAppTextMessage.model_validate(message_data)

    def _create_interactive_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.interactive import (
            WhatsAppInteractiveMessage,
        )

        return WhatsAppInteractiveMessage.model_validate(message_data)

    def _create_image_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.image import WhatsAppImageMessage

        return WhatsAppImageMessage.model_validate(message_data)

    def _create_audio_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.audio import WhatsAppAudioMessage

        return WhatsAppAudioMessage.model_validate(message_data)

    def _create_video_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.video import WhatsAppVideoMessage

        return WhatsAppVideoMessage.model_validate(message_data)

    def _create_document_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.document import (
            WhatsAppDocumentMessage,
        )

        return WhatsAppDocumentMessage.model_validate(message_data)

    def _create_contact_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.contact import WhatsAppContactMessage

        return WhatsAppContactMessage.model_validate(message_data)

    def _create_location_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.location import (
            WhatsAppLocationMessage,
        )

        return WhatsAppLocationMessage.model_validate(message_data)

    def _create_sticker_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.sticker import WhatsAppStickerMessage

        return WhatsAppStickerMessage.model_validate(message_data)

    def _create_system_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.system import WhatsAppSystemMessage

        return WhatsAppSystemMessage.model_validate(message_data)

    def _create_unsupported_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.unsupported import (
            WhatsAppUnsupportedMessage,
        )

        return WhatsAppUnsupportedMessage.model_validate(message_data)

    def _create_reaction_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.reaction import (
            WhatsAppReactionMessage,
        )

        return WhatsAppReactionMessage.model_validate(message_data)

    def _create_button_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.button import WhatsAppButtonMessage

        return WhatsAppButtonMessage.model_validate(message_data)

    def _create_order_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.order import WhatsAppOrderMessage

        return WhatsAppOrderMessage.model_validate(message_data)

    def _create_lifecycle_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        from wappa.webhooks.whatsapp.message_types.lifecycle import (
            WhatsAppLifecycleMessage,
        )

        return WhatsAppLifecycleMessage.model_validate(message_data)

    # ===== Universal Webhook Interface Creation Methods =====

    async def create_universal_webhook(
        self, payload: dict[str, Any], inbox_id: str | None = None, **kwargs
    ) -> "UniversalWebhook":
        try:
            webhook = self.parse_webhook_container(payload)
            self.logger.debug("Raw WhatsApp webhook received: %s", payload)

            inbox_base = self._create_inbox_base(webhook, inbox_id)

            # System events are checked BEFORE incoming messages because system
            # messages (type=="system") arrive in the messages field.
            if webhook.is_system_event:
                universal_webhook = await self._create_system_webhook(
                    webhook, inbox_base, **kwargs
                )
            elif webhook.is_call_event:
                universal_webhook = await self._create_call_webhook(
                    webhook, inbox_base, **kwargs
                )
            elif webhook.is_incoming_message:
                universal_webhook = await self._create_incoming_message_webhook(
                    webhook, inbox_base, **kwargs
                )
            elif webhook.is_status_update:
                universal_webhook = await self._create_status_webhook(
                    webhook, inbox_base, **kwargs
                )
            elif webhook.has_errors:
                universal_webhook = await self._create_error_webhook(
                    webhook, inbox_base, **kwargs
                )
            elif webhook.is_custom_field and self._field_registry is not None:
                universal_webhook = await self._create_custom_webhook(
                    webhook, inbox_base, payload, **kwargs
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
            if isinstance(e, ValidationError):
                self._log_contract_drift(e)
            self.logger.error(
                "Failed to create universal webhook: %s", e, exc_info=True
            )
            raise ProcessorError(
                f"Failed to transform WhatsApp webhook to universal interface: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            ) from e

    def _create_inbox_base(
        self, webhook: BaseWebhook, inbox_id: str | None = None
    ) -> "InboxBase":
        from wappa.webhooks.core.webhook_interfaces import InboxBase

        # Built-in field payloads carry value.metadata with phone number info.
        # Custom registered fields (e.g. message_template_status_update) do
        # not — fall back to the WABA ID + URL-supplied inbox_id.
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
            inbox_id=inbox_id or "",
            display_address="",
            platform_account_id=waba_id,
        )

    async def _create_incoming_message_webhook(
        self, webhook: BaseWebhook, inbox_base: "InboxBase", **kwargs
    ) -> "InboundMessageWebhook":
        from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook

        raw_messages = webhook.get_raw_messages()
        if not raw_messages:
            raise ProcessorError(
                "No messages found in incoming message webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        raw_message = raw_messages[0]
        raw_message_type = raw_message.get("type", "text")

        # WhatsApp uses 'contacts' but the enum uses 'contact'.
        whatsapp_to_universal_type = {"contacts": "contact"}
        universal_message_type = whatsapp_to_universal_type.get(
            raw_message_type, raw_message_type
        )

        message_type = MessageType(universal_message_type)
        message = self.create_message_from_data(raw_message, message_type)

        # Create user base from contacts
        user_base = self._create_user_base_from_contacts(webhook, message.sender_id)
        whatsapp_data = self._create_whatsapp_incoming_data(webhook, message.sender_id)

        # Extract WhatsApp-specific contexts
        business_context = self._extract_business_context(raw_message)
        forward_context = self._extract_forward_context(raw_message)
        ad_referral = self._extract_ad_referral(raw_message)

        return InboundMessageWebhook(
            inbox=inbox_base,
            user=user_base,
            whatsapp=whatsapp_data,
            message=message,
            business_context=business_context,
            forward_context=forward_context,
            ad_referral=ad_referral,
            timestamp=datetime.fromtimestamp(message.timestamp),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    async def _create_call_webhook(
        self, webhook: BaseWebhook, inbox_base: "InboxBase", **kwargs
    ) -> "CallWebhook":
        from wappa.webhooks.core.webhook_interfaces import CallWebhook

        value = webhook.get_call_event()
        if value is None:
            raise ProcessorError(
                "No calls value found in calls webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

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

    async def _create_status_webhook(
        self, webhook: BaseWebhook, inbox_base: "InboxBase", **kwargs
    ) -> "StatusWebhook":
        from wappa.webhooks.core.webhook_interfaces import StatusWebhook

        raw_statuses = webhook.get_raw_statuses()
        if not raw_statuses:
            raise ProcessorError(
                "No statuses found in status webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        # Parse the first status
        raw_status = raw_statuses[0]
        status = self.create_status_from_data(raw_status)

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
            status=getattr(status, "status", "unknown"),
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

    async def _create_error_webhook(
        self, webhook: BaseWebhook, inbox_base: "InboxBase", **kwargs
    ) -> "ErrorWebhook":
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase, ErrorWebhook

        webhook_errors: list[dict[str, Any]] = []
        for entry in webhook.entry:
            for change in entry.changes:
                if change.value.errors:
                    webhook_errors.extend(change.value.errors)

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

    async def _create_custom_webhook(
        self,
        webhook: BaseWebhook,
        inbox_base: "InboxBase",
        payload: dict[str, Any],
        **kwargs,
    ) -> "CustomWebhook":
        """Build a CustomWebhook for an app-registered Meta webhook field.

        Parser failures bubble up as ``ProcessorError`` — a registered field
        whose payload doesn't match the app's schema is a real error, not a
        silent drop.
        """
        from wappa.webhooks.core.webhook_interfaces import CustomWebhook

        change = webhook.entry[0].changes[0]
        field_name = change.field
        handler_spec = self._field_registry.get(field_name)
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

    async def _create_system_webhook(
        self, webhook: BaseWebhook, inbox_base: "InboxBase", **kwargs
    ) -> "SystemWebhook":
        # Handles direct fields and system messages carried by messages[].
        # - field: "user_preferences"           → MARKETING_PREFERENCE
        # - field: "user_id_update"             → USER_ID_CHANGE
        # - field: "messages" (type=="system")  → NUMBER_CHANGE or USER_ID_CHANGE
        from wappa.webhooks.core.webhook_interfaces import (
            SystemEventDetail,
            SystemEventType,
            SystemWebhook,
        )

        field = webhook.entry[0].changes[0].field

        user_base = None
        system_event_type = None
        event_detail = None
        event_timestamp = datetime.now(UTC)

        match field:
            case "user_preferences":
                from wappa.webhooks.whatsapp.system_events import UserPreferenceEntry

                raw_prefs = webhook.get_raw_user_preferences()
                if not raw_prefs:
                    raise ProcessorError(
                        "No user_preferences found in system webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                pref = UserPreferenceEntry.model_validate(raw_prefs[0])

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
                    user_base = self._create_user_base_from_contacts(webhook, sender_id)

            case "user_id_update":
                from wappa.webhooks.whatsapp.system_events import UserIdUpdateEntry

                raw_updates = webhook.get_raw_user_id_updates()
                if not raw_updates:
                    raise ProcessorError(
                        "No user_id_update found in system webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                update = UserIdUpdateEntry.model_validate(raw_updates[0])
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
                    user_base = self._create_user_base_from_contacts(
                        webhook, update.wa_id
                    )

            case "account_offboarded" | "account_reconnected":
                # Coexistence account-level events share one flat WABA-scoped
                # shape (AccountWebhookValue); the field name maps 1:1 to the
                # SystemEventType. Account-scoped: no user context, user stays None.
                account = webhook.get_account_event(field)
                if account is None:
                    raise ProcessorError(
                        f"No {field} found in system webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                system_event_type = SystemEventType(field)
                event_detail = SystemEventDetail(
                    waba_id=account.waba_id,
                    phone_number_id=account.phone_number_id,
                    reason=account.reason,
                )
                event_timestamp = datetime.fromtimestamp(account.timestamp, tz=UTC)

            case "business_username_updates":
                username_event = webhook.get_business_username_event()
                if username_event is None:
                    raise ProcessorError(
                        "No business_username_updates value found in system webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                system_event_type = SystemEventType.BUSINESS_USERNAME_UPDATE
                event_detail = SystemEventDetail(
                    username=username_event.username,
                    username_status=username_event.status,
                    display_phone_number=username_event.display_phone_number,
                )
                entry_time = webhook.entry[0].time
                if entry_time is not None:
                    event_timestamp = datetime.fromtimestamp(entry_time, tz=UTC)

            case "group_participants_update":
                from wappa.webhooks.core.webhook_interfaces import UserBase
                from wappa.webhooks.whatsapp.system_events import (
                    GroupParticipantsUpdateEntry,
                )

                raw_group_updates = webhook.get_raw_group_updates()
                if not raw_group_updates:
                    raise ProcessorError(
                        "No groups found in group_participants_update webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                group_update = GroupParticipantsUpdateEntry.model_validate(
                    raw_group_updates[0]
                )
                participant = None
                if group_update.added_participants:
                    participant = group_update.added_participants[0]
                elif group_update.removed_participants:
                    participant = group_update.removed_participants[0]

                wa_id = group_update.wa_id or (
                    participant.wa_id if participant else None
                )
                user_id = group_update.user_id or (
                    participant.user_id if participant else None
                )
                parent_user_id = group_update.parent_user_id or (
                    participant.parent_user_id if participant else None
                )
                username = group_update.username or (
                    participant.username if participant else None
                )

                system_event_type = SystemEventType.GROUP_PARTICIPANTS_UPDATE
                event_detail = SystemEventDetail(
                    wa_id=wa_id,
                    user_id=user_id,
                    parent_user_id=parent_user_id,
                    group_id=group_update.group_id,
                    group_event_type=group_update.type,
                    group_update=group_update.model_dump(mode="json"),
                )
                event_timestamp = datetime.fromtimestamp(group_update.timestamp, tz=UTC)
                if wa_id or user_id:
                    user_base = UserBase(
                        phone_number=wa_id or "",
                        bsuid=user_id,
                        parent_bsuid=parent_user_id,
                        username=username,
                    )

            case "history" | "smb_message_echoes" | "smb_app_state_sync":
                from wappa.webhooks.core.webhook_interfaces import UserBase
                from wappa.webhooks.whatsapp.coexistence_events import (
                    HistoryWebhookValue,
                    SmbAppStateSyncWebhookValue,
                    SmbMessageEchoesWebhookValue,
                )

                coexistence = webhook.get_coexistence_event()
                if coexistence is None:
                    raise ProcessorError(
                        f"No typed {field} value found in system webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                event_types = {
                    "history": SystemEventType.HISTORY_SYNC,
                    "smb_message_echoes": SystemEventType.SMB_MESSAGE_ECHO,
                    "smb_app_state_sync": SystemEventType.SMB_APP_STATE_SYNC,
                }
                system_event_type = event_types[field]
                event_detail = SystemEventDetail(
                    coexistence_payload=coexistence.model_dump(
                        mode="json", by_alias=True, exclude_none=True
                    )
                )

                if isinstance(coexistence, SmbAppStateSyncWebhookValue):
                    state = coexistence.state_sync[0]
                    contact = state.contact
                    event_timestamp = datetime.fromtimestamp(
                        int(state.metadata.timestamp), tz=UTC
                    )
                    user_base = UserBase(
                        phone_number=contact.phone_number or "",
                        bsuid=contact.user_id,
                        parent_bsuid=contact.parent_user_id,
                        username=contact.username,
                        profile_name=contact.full_name,
                    )
                elif isinstance(coexistence, SmbMessageEchoesWebhookValue):
                    echo = coexistence.message_echoes[0]
                    event_timestamp = datetime.fromtimestamp(
                        int(echo.timestamp), tz=UTC
                    )
                    user_base = self._create_user_base_from_contacts(
                        webhook, echo.to_user_id or echo.to or ""
                    )
                elif isinstance(coexistence, HistoryWebhookValue):
                    identity = None
                    if coexistence.contacts:
                        identity = coexistence.contacts[0].user_id
                    if identity:
                        user_base = self._create_user_base_from_contacts(
                            webhook, identity
                        )

            case "messages":
                # System messages from the messages field (type=="system")
                raw_messages = webhook.get_raw_messages()
                if not raw_messages:
                    raise ProcessorError(
                        "No system messages found in webhook",
                        ErrorCode.PROCESSING_ERROR,
                        PlatformType.WHATSAPP,
                    )

                message = self._create_system_message(raw_messages[0])

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
                        parent_user_id=message.system.parent_user_id,
                        body=message.system_message,
                    )

                event_timestamp = datetime.fromtimestamp(message.timestamp, tz=UTC)
                user_base = self._create_user_base_from_contacts(
                    webhook, message.sender_id
                )

        return SystemWebhook(
            inbox=inbox_base,
            system_event_type=system_event_type,
            event_detail=event_detail,
            user=user_base,
            timestamp=event_timestamp,
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    def _create_user_base_from_contacts(
        self, webhook: BaseWebhook, sender_id: str
    ) -> "UserBase":
        from wappa.webhooks.core.webhook_interfaces import UserBase

        for contact in webhook.get_contacts():
            if contact.user_id == sender_id:
                return UserBase(
                    phone_number=getattr(contact, "wa_id", "") or "",
                    bsuid=getattr(contact, "bsuid", None),
                    parent_bsuid=getattr(contact, "parent_bsuid", None),
                    username=getattr(contact, "username", None),
                    country_code=getattr(contact, "country_code", None),
                    profile_name=contact.display_name,
                    identity_key_hash=getattr(contact, "identity_key_hash", None),
                )

        fallback_phone = sender_id if looks_like_phone_number(sender_id) else ""
        fallback_bsuid = sender_id if looks_like_bsuid(sender_id) else None
        return UserBase(
            phone_number=fallback_phone,
            bsuid=fallback_bsuid,
            parent_bsuid=None,
            username=None,
            country_code=None,
            profile_name=None,
            identity_key_hash=None,
        )

    def _create_whatsapp_incoming_data(
        self, webhook: BaseWebhook, sender_id: str
    ) -> "WhatsAppIncomingWebhookData":
        from wappa.webhooks.core.webhook_interfaces import WhatsAppIncomingWebhookData

        for contact in webhook.get_contacts():
            if contact.user_id == sender_id:
                return WhatsAppIncomingWebhookData(
                    wa_id=getattr(contact, "wa_id", None) or None,
                    bsuid=getattr(contact, "bsuid", None),
                    parent_bsuid=getattr(contact, "parent_bsuid", None),
                    username=getattr(contact, "username", None),
                    country_code=getattr(contact, "country_code", None),
                )

        return WhatsAppIncomingWebhookData(
            wa_id=sender_id if looks_like_phone_number(sender_id) else None,
            bsuid=sender_id if looks_like_bsuid(sender_id) else None,
            parent_bsuid=None,
            username=None,
            country_code=None,
        )

    def _create_status_user_from_contacts(
        self, webhook: BaseWebhook, recipient_id: str
    ) -> "UserBase | None":
        """Build status recipient data when Meta includes the contacts block."""
        contacts = webhook.get_contacts()
        if not contacts:
            return None
        return self._create_user_base_from_contacts(webhook, recipient_id)

    def _extract_business_context(
        self, message_data: dict[str, Any]
    ) -> "BusinessContextBase | None":
        from wappa.webhooks.core.webhook_interfaces import BusinessContextBase

        context = message_data.get("context")
        if not context or not context.get("referred_product"):
            return None

        return BusinessContextBase(
            contextual_message_id=context.get("id", ""),
            business_phone_number=context.get("from", ""),
            catalog_id=context["referred_product"].get("catalog_id"),
            product_retailer_id=context["referred_product"].get("product_retailer_id"),
        )

    def _extract_forward_context(
        self, message_data: dict[str, Any]
    ) -> "ForwardContextBase | None":
        from wappa.webhooks.core.webhook_interfaces import ForwardContextBase

        context = message_data.get("context")
        if not context:
            return None

        is_forwarded = context.get("forwarded", False)
        is_frequently_forwarded = context.get("frequently_forwarded", False)

        if not (is_forwarded or is_frequently_forwarded):
            return None

        return ForwardContextBase(
            is_forwarded=is_forwarded,
            is_frequently_forwarded=is_frequently_forwarded,
            forward_count=None,
            original_sender=None,
        )

    def _extract_ad_referral(
        self, message_data: dict[str, Any]
    ) -> "AdReferralBase | None":
        from wappa.webhooks.core.webhook_interfaces import AdReferralBase

        referral = message_data.get("referral")
        if not referral:
            return None

        return AdReferralBase(
            source_type=referral.get("source_type", "ad"),
            source_id=referral.get("source_id", ""),
            source_url=referral.get("source_url", ""),
            ad_body=referral.get("body"),
            ad_headline=referral.get("headline"),
            media_type=referral.get("media_type"),
            image_url=referral.get("image_url"),
            video_url=referral.get("video_url"),
            thumbnail_url=referral.get("thumbnail_url"),
            click_id=referral.get("ctwa_clid"),
            welcome_message_text=referral.get("welcome_message", {}).get("text"),
        )

    def _extract_conversation_context(
        self, status_data: Any
    ) -> "ConversationBase | None":
        from wappa.webhooks.core.webhook_interfaces import ConversationBase

        conversation = getattr(status_data, "conversation", None)
        if not conversation:
            return None

        pricing = getattr(status_data, "pricing", None)
        origin = getattr(conversation, "origin", None)
        origin_type = getattr(origin, "type", None) if origin else None

        return ConversationBase(
            conversation_id=getattr(conversation, "id", ""),
            expiration_timestamp=getattr(conversation, "expiration_timestamp", None),
            category=origin_type,
            origin_type=origin_type,
            is_billable=getattr(pricing, "billable", None) if pricing else None,
            pricing_model=getattr(pricing, "pricing_model", None) if pricing else None,
            pricing_category=getattr(pricing, "category", None) if pricing else None,
            pricing_type=getattr(pricing, "type", None) if pricing else None,
        )

    def _extract_status_errors(
        self, status_data: Any
    ) -> "list[ErrorDetailBase] | None":
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase

        errors = getattr(status_data, "errors", None)
        if not errors:
            return None

        error_details = []
        for error in errors:
            error_data = getattr(error, "error_data", None)
            error_details.append(
                ErrorDetailBase(
                    error_code=getattr(error, "code", 0),
                    error_title=getattr(error, "title", "Unknown error"),
                    error_message=getattr(error, "message", ""),
                    error_details=getattr(error_data, "details", None)
                    if error_data
                    else None,
                    documentation_url=getattr(error, "href", None),
                    error_type="delivery_failure",
                    occurred_at=datetime.now(UTC),
                )
            )

        return error_details
