"""
Universal Webhook Interface definitions for platform-agnostic webhook handling.

This module defines the 4 universal webhook types that all messaging platforms
must transform their webhooks into:

1. IncomingMessageWebhook - All user-sent messages (text, media, interactive, etc.)
2. StatusWebhook - Message delivery status updates (sent, delivered, read, failed)
3. ErrorWebhook - System, app, and account-level errors
4. OutgoingMessageWebhook - Business-sent message tracking (future feature)

These interfaces represent the "universal standard" based on WhatsApp's comprehensive
webhook structure. All platforms (Teams, Telegram, Instagram) must adapt to these.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.types import MessageStatus, PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    AdReferralBase,
    BusinessContextBase,
    ConversationBase,
    ErrorDetailBase,
    ForwardContextBase,
    TenantBase,
    UserBase,
)


class IncomingMessageWebhook(BaseModel):
    """
    Universal interface for all incoming messages from users to businesses.

    This interface represents any message sent by a user to a business,
    regardless of platform or message type. It includes the core message
    content plus optional context for advanced features.

    All platforms must transform their incoming message webhooks to this format.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core identification
    tenant: TenantBase = Field(description="Business/tenant identification")
    user: UserBase = Field(description="User/sender identification")

    # Message content (supports all message types)
    message: BaseMessage = Field(
        description="The actual message content with unified interface"
    )

    # Optional contexts (WhatsApp-based features that should be universal)
    business_context: BusinessContextBase | None = Field(
        default=None,
        description="Context when message originated from business interactions (catalogs, buttons)",
    )
    forward_context: ForwardContextBase | None = Field(
        default=None, description="Context when message was forwarded by the user"
    )
    ad_referral: AdReferralBase | None = Field(
        default=None,
        description="Context when message originated from advertisement interaction",
    )

    # Universal metadata
    timestamp: datetime = Field(description="When the message was received")
    platform: PlatformType = Field(description="Source messaging platform")

    # Webhook identification
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    # Raw webhook data (for debugging and inspection)
    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,  # Don't include in serialization by default
    )

    def get_message_text(self) -> str:
        """
        Get text content from the message, regardless of message type.

        Returns:
            Text content or empty string if no text available
        """
        # For text messages, get the text_content property
        if hasattr(self.message, "text_content"):
            return self.message.text_content

        # For interactive messages, try to get the selection value
        interactive_value = self.get_interactive_selection()
        if interactive_value:
            return interactive_value

        return ""

    def get_message_type_name(self) -> str:
        """Get the message type as a string."""
        return self.message.message_type.value

    def get_interactive_selection(self) -> str | None:
        """
        Get the selected option from interactive messages.

        Returns:
            The selected option ID/value or None if not an interactive message
        """
        # Check if this is an interactive message
        if self.get_message_type_name() != "interactive":
            return None

        # Try to get the selected option ID from the message
        if hasattr(self.message, "selected_option_id"):
            return self.message.selected_option_id

        # Fallback: try to get interactive data directly (platform-specific)
        if hasattr(self.message, "interactive"):
            interactive_data = getattr(self.message, "interactive", {})

            # Handle button replies
            if (
                hasattr(interactive_data, "type")
                and interactive_data.type == "button_reply"
            ):
                button_reply = getattr(interactive_data, "button_reply", None)
                if button_reply and hasattr(button_reply, "id"):
                    return button_reply.id

            # Handle list replies
            elif (
                hasattr(interactive_data, "type")
                and interactive_data.type == "list_reply"
            ):
                list_reply = getattr(interactive_data, "list_reply", None)
                if list_reply and hasattr(list_reply, "id"):
                    return list_reply.id

        return None

    def has_business_context(self) -> bool:
        """Check if this message has business interaction context."""
        return self.business_context is not None

    def has_ad_referral(self) -> bool:
        """Check if this message originated from an advertisement."""
        return self.ad_referral is not None

    def was_forwarded(self) -> bool:
        """Check if this message was forwarded."""
        return self.forward_context is not None and self.forward_context.is_forwarded

    def get_conversation_id(self) -> str:
        """Get conversation ID from the message."""
        return getattr(self.message, "conversation_id", "")

    def get_sender_display_name(self) -> str:
        """Get sender's display name."""
        return self.user.get_display_name()

    def get_raw_webhook_data(self) -> dict | None:
        """
        Get the original raw webhook JSON payload.

        This is useful for debugging, logging, or accessing platform-specific
        fields that aren't included in the universal interface.

        Returns:
            Original webhook JSON dict or None if not available
        """
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """
        Set the original raw webhook JSON payload.

        This should be called by webhook processors when creating
        UniversalWebhook instances.

        Args:
            raw_data: Original webhook JSON payload
        """
        self.raw_webhook_data = raw_data

    def get_summary(self) -> dict[str, any]:
        """
        Get a summary of this webhook for logging and monitoring.

        Returns:
            Dictionary with key information about this webhook
        """
        return {
            "webhook_type": "incoming_message",
            "platform": self.platform.value,
            "message_type": self.get_message_type_name(),
            "sender": self.user.user_id,
            "tenant": self.tenant.get_tenant_key(),
            "has_business_context": self.has_business_context(),
            "has_ad_referral": self.has_ad_referral(),
            "was_forwarded": self.was_forwarded(),
            "timestamp": self.timestamp.isoformat(),
        }


class StatusWebhook(BaseModel):
    """
    Universal interface for message delivery status updates.

    This interface represents status updates for messages sent by businesses
    to users (sent, delivered, read, failed). It includes conversation and
    billing context when available.

    All platforms must transform their status webhooks to this format.

    BSUID Support (v24.0+):
    - recipient_phone_id: Raw phone-based recipient ID from webhook
    - recipient_bsuid: Business Scoped User ID (stable identifier)
    - recipient_id: Property that returns BSUID if available, else recipient_phone_id
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core identification
    tenant: TenantBase = Field(description="Business/tenant identification")

    # Status information
    message_id: str = Field(description="ID of the message this status refers to")
    status: MessageStatus = Field(description="Current status of the message")
    recipient_phone_id: str = Field(
        default="",
        description="Raw phone-based recipient ID from webhook (may be empty for BSUID-only)",
    )
    recipient_bsuid: str | None = Field(
        default=None,
        description="Business Scoped User ID of the recipient - stable identifier",
    )
    timestamp: datetime = Field(description="When this status update occurred")

    # Optional context
    conversation: ConversationBase | None = Field(
        default=None, description="Conversation and billing context (if available)"
    )

    # Error context (for failed status)
    errors: list[ErrorDetailBase] | None = Field(
        default=None, description="Error details if status indicates failure"
    )

    # Optional business metadata
    business_opaque_data: str | None = Field(
        default=None,
        description="Business-provided tracking data from original message",
    )

    # Security context
    recipient_identity_hash: str | None = Field(
        default=None, description="Recipient identity key hash for security validation"
    )

    # Universal metadata
    platform: PlatformType = Field(description="Source messaging platform")
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    # Raw webhook data (for debugging and inspection)
    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,  # Don't include in serialization by default
    )

    @property
    def recipient_id(self) -> str:
        """
        Get the recommended recipient identifier.

        Returns:
            BSUID if available, otherwise falls back to recipient_phone_id.
        """
        if self.recipient_bsuid and self.recipient_bsuid.strip():
            return self.recipient_bsuid.strip()
        return self.recipient_phone_id

    @property
    def has_recipient_bsuid(self) -> bool:
        """Check if this status has a recipient BSUID set."""
        return bool(self.recipient_bsuid and self.recipient_bsuid.strip())

    @property
    def has_recipient_phone(self) -> bool:
        """Check if this status has a recipient phone/ID set."""
        return bool(self.recipient_phone_id and self.recipient_phone_id.strip())

    def is_delivered_status(self) -> bool:
        """Check if this status indicates successful delivery."""
        return self.status in [MessageStatus.DELIVERED, MessageStatus.READ]

    def is_failed_status(self) -> bool:
        """Check if this status indicates failure."""
        return self.status == MessageStatus.FAILED

    def has_errors(self) -> bool:
        """Check if this status includes error information."""
        return self.errors is not None and len(self.errors) > 0

    def get_primary_error(self) -> ErrorDetailBase | None:
        """Get the primary error if this status failed."""
        if not self.has_errors():
            return None
        return self.errors[0]

    def is_billable_message(self) -> bool:
        """Check if this message is billable."""
        if self.conversation is None:
            return False
        return not self.conversation.is_free_conversation()

    def get_summary(self) -> dict[str, any]:
        """
        Get a summary of this webhook for logging and monitoring.

        Returns:
            Dictionary with key information about this webhook
        """
        return {
            "webhook_type": "status",
            "platform": self.platform.value,
            "status": self.status.value,
            "message_id": self.message_id,
            "recipient": self.recipient_id,
            "recipient_bsuid": self.recipient_bsuid,
            "has_recipient_bsuid": self.has_recipient_bsuid,
            "tenant": self.tenant.get_tenant_key(),
            "is_billable": self.is_billable_message(),
            "has_errors": self.has_errors(),
            "timestamp": self.timestamp.isoformat(),
        }

    def get_raw_webhook_data(self) -> dict | None:
        """
        Get the original raw webhook JSON payload.

        This is useful for debugging, logging, or accessing platform-specific
        fields that aren't included in the universal interface.

        Returns:
            Original webhook JSON dict or None if not available
        """
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """
        Set the original raw webhook JSON payload.

        This should be called by webhook processors when creating
        UniversalWebhook instances.

        Args:
            raw_data: Original webhook JSON payload
        """
        self.raw_webhook_data = raw_data


class ErrorWebhook(BaseModel):
    """
    Universal interface for system, app, and account-level errors.

    This interface represents errors that occur at the platform level,
    not related to specific message delivery (those are in StatusWebhook).

    All platforms must transform their error webhooks to this format.
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Core identification
    tenant: TenantBase = Field(description="Business/tenant identification")

    # Error information
    errors: list[ErrorDetailBase] = Field(description="Detailed error information")
    timestamp: datetime = Field(description="When these errors occurred")

    # Error context
    error_level: str = Field(
        default="system", description="Level of error (system, app, account, webhook)"
    )

    # Universal metadata
    platform: PlatformType = Field(description="Source messaging platform")
    webhook_id: str = Field(description="Unique identifier for this webhook event")

    # Raw webhook data (for debugging and inspection)
    raw_webhook_data: dict | None = Field(
        default=None,
        description="Original raw webhook JSON payload",
        exclude=True,  # Don't include in serialization by default
    )

    def get_primary_error(self) -> ErrorDetailBase:
        """Get the primary (first) error."""
        return self.errors[0]

    def get_error_count(self) -> int:
        """Get total number of errors in this webhook."""
        return len(self.errors)

    def has_critical_errors(self) -> bool:
        """Check if any errors are likely critical (5xx codes)."""
        return any(500 <= error.error_code < 600 for error in self.errors)

    def has_retryable_errors(self) -> bool:
        """Check if any errors are potentially retryable."""
        return any(error.is_temporary_error() for error in self.errors)

    def get_error_codes(self) -> list[int]:
        """Get list of all error codes in this webhook."""
        return [error.error_code for error in self.errors]

    def get_summary(self) -> dict[str, any]:
        """
        Get a summary of this webhook for logging and monitoring.

        Returns:
            Dictionary with key information about this webhook
        """
        return {
            "webhook_type": "error",
            "platform": self.platform.value,
            "error_level": self.error_level,
            "error_count": self.get_error_count(),
            "error_codes": self.get_error_codes(),
            "tenant": self.tenant.get_tenant_key(),
            "has_critical_errors": self.has_critical_errors(),
            "has_retryable_errors": self.has_retryable_errors(),
            "timestamp": self.timestamp.isoformat(),
        }

    def get_raw_webhook_data(self) -> dict | None:
        """
        Get the original raw webhook JSON payload.

        This is useful for debugging, logging, or accessing platform-specific
        fields that aren't included in the universal interface.

        Returns:
            Original webhook JSON dict or None if not available
        """
        return self.raw_webhook_data

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        """
        Set the original raw webhook JSON payload.

        This should be called by webhook processors when creating
        UniversalWebhook instances.

        Args:
            raw_data: Original webhook JSON payload
        """
        self.raw_webhook_data = raw_data


# Type union for all universal webhook interfaces
# Note: "Outgoing message" webhooks are actually status updates and use StatusWebhook
UniversalWebhook = IncomingMessageWebhook | StatusWebhook | ErrorWebhook
