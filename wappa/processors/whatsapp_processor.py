"""
WhatsApp webhook processor for the Mimeia AI Agent Platform.

This module provides comprehensive WhatsApp Business Platform webhook processing,
including message parsing, validation, and integration with the Symphony AI system.
"""

import hashlib
import hmac
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from wappa.core.config.settings import settings
from wappa.core.logging.context import set_request_context
from wappa.processors.base_processor import (
    BaseWebhookProcessor,
    # ProcessingResult removed - Universal Webhook Interface is the ONLY way
    ProcessorCapabilities,
    ProcessorError,
)
from wappa.schemas.core.types import ErrorCode, MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.base_status import BaseMessageStatus
from wappa.webhooks.core.base_webhook import BaseWebhook


class WhatsAppWebhookProcessor(BaseWebhookProcessor):
    """
    WhatsApp Business Platform webhook processor.

    Handles parsing, validation, and processing of WhatsApp webhooks
    including incoming messages and outgoing message status updates.
    Inherits from BaseWebhookProcessor for platform-agnostic interface.
    """

    def __init__(self):
        """Initialize the WhatsApp processor with capabilities and handlers."""
        super().__init__()

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
        """Get the platform this processor handles."""
        return PlatformType.WHATSAPP

    @property
    def capabilities(self) -> ProcessorCapabilities:
        """Get the capabilities of this processor."""
        return self._capabilities

    def _register_message_handlers(self) -> None:
        """Register handlers for all supported WhatsApp message types."""
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

    # Legacy process_webhook method removed - Universal Webhook Interface is now the ONLY way
    # Use create_universal_webhook() method instead for type-safe webhook handling

    def validate_webhook_signature(
        self, payload: bytes, signature: str, **kwargs
    ) -> bool:
        """
        Validate WhatsApp webhook signature for security.

        Args:
            payload: Raw webhook payload bytes
            signature: X-Hub-Signature-256 header from WhatsApp
            **kwargs: Additional validation parameters

        Returns:
            True if signature is valid, False otherwise
        """
        if not settings.whatsapp_webhook_verify_token:
            self.logger.warning(
                "WhatsApp webhook verification token not configured - skipping signature validation"
            )
            return True

        try:
            # WhatsApp sends signature as 'sha256=<hash>'
            if not signature.startswith("sha256="):
                self.logger.error(
                    "Invalid signature format - must start with 'sha256='"
                )
                return False

            # Extract the hash part
            provided_hash = signature[7:]  # Remove 'sha256=' prefix

            # Calculate expected hash
            expected_hash = hmac.new(
                settings.whatsapp_webhook_verify_token.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()

            # Compare hashes securely
            is_valid = hmac.compare_digest(expected_hash, provided_hash)

            if not is_valid:
                self.logger.error("Webhook signature validation failed")

            return is_valid

        except Exception as e:
            self.logger.error(f"Error validating webhook signature: {e}", exc_info=True)
            return False

    def parse_webhook_container(self, payload: dict[str, Any], **kwargs) -> BaseWebhook:
        """
        Parse the top-level WhatsApp webhook structure.

        Args:
            payload: Raw webhook payload
            **kwargs: Additional parsing parameters

        Returns:
            Parsed webhook container with universal interface

        Raises:
            ValidationError: If webhook structure is invalid
        """
        try:
            from wappa.webhooks.whatsapp.webhook_container import WhatsAppWebhook

            webhook = WhatsAppWebhook.model_validate(payload)

            self.logger.debug(
                f"Successfully parsed WhatsApp webhook from {webhook.business_id}"
            )
            return webhook

        except ValidationError as e:
            error_msg = f"Failed to parse WhatsApp webhook structure: {e}"
            self.logger.error(error_msg)
            raise ValueError(error_msg) from e

    def get_supported_message_types(self) -> set[MessageType]:
        """Get the set of message types this processor supports."""
        return self._capabilities.supported_message_types

    def create_message_from_data(
        self, message_data: dict[str, Any], message_type: MessageType, **kwargs
    ) -> BaseMessage:
        """
        Create a message instance from raw data.

        Args:
            message_data: Raw message data from webhook
            message_type: The type of message to create
            **kwargs: Additional creation parameters

        Returns:
            Parsed message with universal interface

        Raises:
            ValidationError: If message data is invalid
            UnsupportedMessageType: If message type is not supported
        """
        # Use the mapped universal message type for handler lookup instead of raw type
        message_type_str = message_type.value

        # Get appropriate handler
        handler = self.get_message_handler(message_type_str)
        if handler is None:
            from .base_processor import UnsupportedMessageTypeError

            raise UnsupportedMessageTypeError(message_type_str, self.platform)

        # Create message instance
        return handler(message_data, **kwargs)

    def create_status_from_data(
        self, status_data: dict[str, Any], **kwargs
    ) -> BaseMessageStatus:
        """
        Create a status instance from raw data.

        Args:
            status_data: Raw status data from webhook
            **kwargs: Additional creation parameters

        Returns:
            Parsed status with universal interface

        Raises:
            ValidationError: If status data is invalid
        """
        try:
            from wappa.webhooks.whatsapp.status_models import WhatsAppMessageStatus

            return WhatsAppMessageStatus.model_validate(status_data)

        except ValidationError as e:
            self.logger.error(f"Failed to parse WhatsApp message status: {e}")
            raise

    # Legacy _process_webhook_errors method removed - Universal Webhook Interface handles errors via ErrorWebhook

    # Message creation handlers for all WhatsApp message types

    def _create_text_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a text message instance."""
        from wappa.webhooks.whatsapp.message_types.text import WhatsAppTextMessage

        return WhatsAppTextMessage.model_validate(message_data)

    def _create_interactive_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create an interactive message instance."""
        from wappa.webhooks.whatsapp.message_types.interactive import (
            WhatsAppInteractiveMessage,
        )

        return WhatsAppInteractiveMessage.model_validate(message_data)

    def _create_image_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create an image message instance."""
        from wappa.webhooks.whatsapp.message_types.image import WhatsAppImageMessage

        return WhatsAppImageMessage.model_validate(message_data)

    def _create_audio_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create an audio message instance."""
        from wappa.webhooks.whatsapp.message_types.audio import WhatsAppAudioMessage

        return WhatsAppAudioMessage.model_validate(message_data)

    def _create_video_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a video message instance."""
        from wappa.webhooks.whatsapp.message_types.video import WhatsAppVideoMessage

        return WhatsAppVideoMessage.model_validate(message_data)

    def _create_document_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a document message instance."""
        from wappa.webhooks.whatsapp.message_types.document import (
            WhatsAppDocumentMessage,
        )

        return WhatsAppDocumentMessage.model_validate(message_data)

    def _create_contact_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a contact message instance."""
        from wappa.webhooks.whatsapp.message_types.contact import WhatsAppContactMessage

        return WhatsAppContactMessage.model_validate(message_data)

    def _create_location_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a location message instance."""
        from wappa.webhooks.whatsapp.message_types.location import (
            WhatsAppLocationMessage,
        )

        return WhatsAppLocationMessage.model_validate(message_data)

    def _create_sticker_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a sticker message instance."""
        from wappa.webhooks.whatsapp.message_types.sticker import WhatsAppStickerMessage

        return WhatsAppStickerMessage.model_validate(message_data)

    def _create_system_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a system message instance."""
        from wappa.webhooks.whatsapp.message_types.system import WhatsAppSystemMessage

        return WhatsAppSystemMessage.model_validate(message_data)

    def _create_unsupported_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create an unsupported message instance."""
        from wappa.webhooks.whatsapp.message_types.unsupported import (
            WhatsAppUnsupportedMessage,
        )

        return WhatsAppUnsupportedMessage.model_validate(message_data)

    def _create_reaction_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a reaction message instance."""
        from wappa.webhooks.whatsapp.message_types.reaction import (
            WhatsAppReactionMessage,
        )

        return WhatsAppReactionMessage.model_validate(message_data)

    def _create_button_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create a button message instance."""
        from wappa.webhooks.whatsapp.message_types.button import WhatsAppButtonMessage

        return WhatsAppButtonMessage.model_validate(message_data)

    def _create_order_message(
        self, message_data: dict[str, Any], **kwargs
    ) -> BaseMessage:
        """Create an order message instance."""
        from wappa.webhooks.whatsapp.message_types.order import WhatsAppOrderMessage

        return WhatsAppOrderMessage.model_validate(message_data)

    # ===== Universal Webhook Interface Creation Methods =====

    async def create_universal_webhook(
        self, payload: dict[str, Any], tenant_id: str | None = None, **kwargs
    ) -> "UniversalWebhook":
        """
        Transform WhatsApp webhook into Universal Webhook Interface.

        This is the main adapter method that converts WhatsApp-specific webhook
        payload into one of the 4 universal webhook types.

        Args:
            payload: Raw WhatsApp webhook payload
            tenant_id: Tenant identifier for context
            **kwargs: Additional processing parameters

        Returns:
            Universal webhook interface (IncomingMessageWebhook, StatusWebhook, or ErrorWebhook)

        Raises:
            ProcessorError: If webhook type cannot be determined or conversion fails
        """

        try:
            # Parse webhook container first
            webhook = self.parse_webhook_container(payload)

            # Log raw webhook payload for debugging
            self.logger.debug(f"📨 Raw WhatsApp webhook received: {payload}")

            # Create tenant base from webhook metadata
            tenant_base = self._create_tenant_base(webhook, tenant_id)

            # Determine webhook type and create appropriate universal interface
            if webhook.is_incoming_message:
                universal_webhook = await self._create_incoming_message_webhook(
                    webhook, tenant_base, **kwargs
                )
            elif webhook.is_status_update:
                universal_webhook = await self._create_status_webhook(
                    webhook, tenant_base, **kwargs
                )
            elif webhook.has_errors:
                universal_webhook = await self._create_error_webhook(
                    webhook, tenant_base, **kwargs
                )
            else:
                universal_webhook = None

            # Set raw webhook data for debugging and inspection
            if universal_webhook is not None:
                universal_webhook.set_raw_webhook_data(payload)

                # Set 3-context system: owner_id (URL), tenant_id (JSON), user_id (JSON)
                webhook_tenant_id = tenant_base.platform_tenant_id  # From JSON metadata

                # Extract user_id based on webhook type
                webhook_user_id = None
                if hasattr(universal_webhook, "user") and universal_webhook.user:
                    # IncomingMessageWebhook has user object
                    webhook_user_id = universal_webhook.user.user_id
                elif hasattr(universal_webhook, "recipient_id"):
                    # StatusWebhook has recipient_id field
                    webhook_user_id = universal_webhook.recipient_id
                # ErrorWebhook has no user context (system-level errors)

                # Set the context with webhook-extracted values
                set_request_context(
                    tenant_id=webhook_tenant_id,  # JSON tenant (authoritative)
                    user_id=webhook_user_id,  # JSON user
                    # Note: owner_id is set by middleware from URL/settings
                )

                self.logger.debug(
                    f"✅ Set webhook context - tenant_id: {webhook_tenant_id}, user_id: {webhook_user_id}"
                )

                return universal_webhook

            # Handle unknown webhook type
            if universal_webhook is None:
                # This could be an outgoing message webhook in the future
                # For now, treat as error
                from wappa.webhooks.core.webhook_interfaces import (
                    ErrorDetailBase,
                    ErrorWebhook,
                )

                error_detail = ErrorDetailBase(
                    error_code=400,
                    error_title="Unknown webhook type",
                    error_message="Webhook contains no recognizable content (messages, statuses, or errors)",
                    error_type="webhook_format",
                    occurred_at=datetime.utcnow(),
                )

                return ErrorWebhook(
                    tenant=tenant_base,
                    errors=[error_detail],
                    timestamp=datetime.utcnow(),
                    error_level="webhook",
                    platform=PlatformType.WHATSAPP,
                    webhook_id=webhook.get_webhook_id(),
                )

        except Exception as e:
            self.logger.error(f"Failed to create universal webhook: {e}", exc_info=True)
            raise ProcessorError(
                f"Failed to transform WhatsApp webhook to universal interface: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            ) from e

    def _create_tenant_base(
        self, webhook: BaseWebhook, tenant_id: str | None = None
    ) -> "TenantBase":
        """
        Create TenantBase from WhatsApp webhook metadata.

        Args:
            webhook: Parsed WhatsApp webhook container
            tenant_id: Optional tenant identifier override

        Returns:
            TenantBase with business identification information
        """
        from wappa.webhooks.core.webhook_interfaces import TenantBase

        # Extract metadata from WhatsApp webhook (metadata is wrapped, access underlying data)
        metadata = webhook.get_metadata()

        # Access the wrapped WhatsApp metadata
        whatsapp_metadata = metadata._metadata

        return TenantBase(
            business_phone_number_id=whatsapp_metadata.phone_number_id,
            display_phone_number=whatsapp_metadata.display_phone_number,
            # For WhatsApp, the phone_number_id IS the tenant identifier
            platform_tenant_id=whatsapp_metadata.phone_number_id,
        )

    async def _create_incoming_message_webhook(
        self, webhook: BaseWebhook, tenant_base: "TenantBase", **kwargs
    ) -> "IncomingMessageWebhook":
        """
        Create IncomingMessageWebhook from WhatsApp messages webhook.

        Args:
            webhook: Parsed WhatsApp webhook container
            tenant_base: Tenant identification information
            **kwargs: Additional processing parameters

        Returns:
            IncomingMessageWebhook with message and context information
        """
        from wappa.webhooks.core.webhook_interfaces import IncomingMessageWebhook

        # Get the first message (WhatsApp typically sends one message per webhook)
        raw_messages = webhook.get_raw_messages()
        if not raw_messages:
            raise ProcessorError(
                "No messages found in incoming message webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )

        # Parse the first message using the message type
        raw_message = raw_messages[0]
        raw_message_type = raw_message.get("type", "text")

        # Map WhatsApp message types to universal message types
        whatsapp_to_universal_type = {
            "contacts": "contact",  # WhatsApp uses 'contacts' but our enum uses 'contact'
            # Add other mappings as needed
        }
        universal_message_type = whatsapp_to_universal_type.get(
            raw_message_type, raw_message_type
        )

        message_type = MessageType(universal_message_type)
        message = self.create_message_from_data(raw_message, message_type)

        # Create user base from contacts
        user_base = self._create_user_base_from_contacts(webhook, message.sender_id)

        # Extract WhatsApp-specific contexts
        business_context = self._extract_business_context(raw_message)
        forward_context = self._extract_forward_context(raw_message)
        ad_referral = self._extract_ad_referral(raw_message)

        return IncomingMessageWebhook(
            tenant=tenant_base,
            user=user_base,
            message=message,
            business_context=business_context,
            forward_context=forward_context,
            ad_referral=ad_referral,
            timestamp=datetime.fromtimestamp(message.timestamp),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    async def _create_status_webhook(
        self, webhook: BaseWebhook, tenant_base: "TenantBase", **kwargs
    ) -> "StatusWebhook":
        """
        Create StatusWebhook from WhatsApp status webhook.

        Args:
            webhook: Parsed WhatsApp webhook container
            tenant_base: Tenant identification information
            **kwargs: Additional processing parameters

        Returns:
            StatusWebhook with message status information
        """
        from wappa.webhooks.core.webhook_interfaces import (
            StatusWebhook,
        )

        # Get the first status (WhatsApp typically sends one status per webhook)
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

        return StatusWebhook(
            tenant=tenant_base,
            message_id=getattr(status, "message_id", ""),
            status=getattr(status, "status", "unknown"),
            recipient_phone_id=getattr(
                status, "wa_recipient_id", ""
            ),  # Phone number field
            recipient_bsuid=getattr(
                status, "recipient_bsuid", None
            ),  # BSUID field (v24.0+)
            timestamp=datetime.fromtimestamp(getattr(status, "timestamp", 0)),
            conversation=conversation,
            errors=errors,
            business_opaque_data=getattr(status, "business_opaque_data", None),
            recipient_identity_hash=getattr(status, "recipient_identity_hash", None),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    async def _create_error_webhook(
        self, webhook: BaseWebhook, tenant_base: "TenantBase", **kwargs
    ) -> "ErrorWebhook":
        """
        Create ErrorWebhook from WhatsApp error webhook.

        Args:
            webhook: Parsed WhatsApp webhook container
            tenant_base: Tenant identification information
            **kwargs: Additional processing parameters

        Returns:
            ErrorWebhook with error information
        """
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase, ErrorWebhook

        # Get errors from webhook (assuming the webhook has error data)
        # For now, we'll extract from raw webhook data since there's no get_errors method
        webhook_errors = []

        # Convert to ErrorDetailBase list
        error_details = []
        for error in webhook_errors:
            error_detail = ErrorDetailBase(
                error_code=getattr(error, "code", 0),
                error_title=getattr(error, "title", "Unknown error"),
                error_message=getattr(error, "message", ""),
                error_details=getattr(error, "details", None),
                documentation_url=getattr(error, "href", None),
                error_type="whatsapp_api",
                occurred_at=datetime.utcnow(),
            )
            error_details.append(error_detail)

        return ErrorWebhook(
            tenant=tenant_base,
            errors=error_details,
            timestamp=datetime.utcnow(),
            error_level="system",
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    def _create_user_base_from_contacts(
        self, webhook: BaseWebhook, sender_id: str
    ) -> "UserBase":
        """
        Create UserBase from WhatsApp contacts information.

        Args:
            webhook: Parsed WhatsApp webhook container
            sender_id: Sender's user ID to match

        Returns:
            UserBase with user identification information
        """
        from wappa.webhooks.core.webhook_interfaces import UserBase

        # Get contacts from webhook
        contacts = webhook.get_contacts()

        # Find matching contact
        for contact in contacts:
            if contact.user_id == sender_id:
                return UserBase(
                    platform_user_id=contact.user_id,  # BSUID-aware identifier (BSUID if available, else phone)
                    phone_number=contact.user_id,  # For backwards compatibility
                    bsuid=contact.bsuid
                    if hasattr(contact, "bsuid")
                    else None,  # BSUID if present (v24.0+)
                    username=contact.username
                    if hasattr(contact, "username")
                    else None,  # Username if present (v24.0+)
                    country_code=contact.country_code
                    if hasattr(contact, "country_code")
                    else None,  # Country code if present (v24.0+)
                    profile_name=contact.display_name,
                    identity_key_hash=contact.identity_key_hash
                    if hasattr(contact, "identity_key_hash")
                    else None,
                )

        # Fallback if no matching contact found
        return UserBase(
            platform_user_id=sender_id,
            phone_number=sender_id,
            bsuid=None,  # No BSUID available
            username=None,
            country_code=None,
            profile_name=None,
            identity_key_hash=None,
        )

    def _extract_business_context(
        self, message_data: dict[str, Any]
    ) -> "BusinessContextBase | None":
        """Extract business context from WhatsApp message data."""
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
        """Extract forward context from WhatsApp message data."""
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
            forward_count=None,  # WhatsApp doesn't provide exact count
            original_sender=None,  # WhatsApp doesn't provide original sender for privacy
        )

    def _extract_ad_referral(
        self, message_data: dict[str, Any]
    ) -> "AdReferralBase | None":
        """Extract ad referral context from WhatsApp message data."""
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
        """Extract conversation context from WhatsApp status data."""
        from wappa.webhooks.core.webhook_interfaces import ConversationBase

        # Check if status has conversation data
        if not hasattr(status_data, "conversation") or not status_data.conversation:
            return None

        conversation = status_data.conversation
        pricing = getattr(status_data, "pricing", None)

        return ConversationBase(
            conversation_id=getattr(conversation, "id", ""),
            expiration_timestamp=getattr(conversation, "expiration_timestamp", None),
            category=getattr(conversation.origin, "type", None)
            if hasattr(conversation, "origin")
            else None,
            origin_type=getattr(conversation.origin, "type", None)
            if hasattr(conversation, "origin")
            else None,
            is_billable=getattr(pricing, "billable", None) if pricing else None,
            pricing_model=getattr(pricing, "pricing_model", None) if pricing else None,
            pricing_category=getattr(pricing, "category", None) if pricing else None,
            pricing_type=getattr(pricing, "type", None) if pricing else None,
        )

    def _extract_status_errors(
        self, status_data: Any
    ) -> "list[ErrorDetailBase] | None":
        """Extract error details from WhatsApp status data."""
        from wappa.webhooks.core.webhook_interfaces import ErrorDetailBase

        if not hasattr(status_data, "errors") or not status_data.errors:
            return None

        error_details = []
        for error in status_data.errors:
            error_detail = ErrorDetailBase(
                error_code=getattr(error, "code", 0),
                error_title=getattr(error, "title", "Unknown error"),
                error_message=getattr(error, "message", ""),
                error_details=getattr(error.error_data, "details", None)
                if hasattr(error, "error_data") and error.error_data
                else None,
                documentation_url=getattr(error, "href", None),
                error_type="delivery_failure",
                occurred_at=datetime.utcnow(),
            )
            error_details.append(error_detail)

        return error_details
