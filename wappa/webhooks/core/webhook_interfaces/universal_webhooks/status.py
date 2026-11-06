"""Universal status webhook: message delivery status updates."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import MessageStatus, PlatformType
from wappa.webhooks.core.webhook_interfaces.base_components import (
    ConversationBase,
    ErrorDetailBase,
    InboxBase,
    UserBase,
)


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
    inbox: InboxBase = Field(description="Business inbox identification")

    # Status information
    message_id: str = Field(description="ID of the message this status refers to")
    status: MessageStatus = Field(description="Current status of the message")
    recipient_platform_id: str | None = Field(
        default=None,
        description=(
            "Native recipient ID, set when the Platform identifies the User by "
            "its own ID instead of address evidence"
        ),
    )
    recipient_phone_id: str = Field(
        default="",
        description="Raw phone-based recipient ID from webhook (may be empty for BSUID-only)",
    )
    recipient_bsuid: str | None = Field(
        default=None,
        description="Business Scoped User ID of the recipient - stable identifier",
    )
    recipient_parent_bsuid: str | None = Field(
        default=None,
        description="Parent Business Scoped User ID of the recipient",
    )
    user: UserBase | None = Field(
        default=None,
        description="Recipient profile supplied in Meta status contacts, when present",
    )
    recipient_type: str | None = Field(
        default=None,
        description="Recipient type such as group",
    )
    recipient_participant_phone_id: str | None = Field(
        default=None,
        description="Group participant phone number, when available",
    )
    recipient_participant_bsuid: str | None = Field(
        default=None,
        description="Group participant BSUID, when available",
    )
    recipient_participant_parent_bsuid: str | None = Field(
        default=None,
        description="Group participant parent BSUID, when available",
    )
    user_id: str | None = Field(
        default=None,
        description=(
            "Canonical domain identifier for the recipient. Populated by the "
            "webhook pipeline: uses the participant BSUID or phone for group "
            "delivery events, otherwise `recipient_id` (BSUID > phone), and "
            "may be enriched via persistence lookup when Meta sends only a "
            "wa_id but a canonical user exists in the store. Use this as the "
            "state/cache key in status handlers."
        ),
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
        if self.recipient_platform_id:
            return self.recipient_platform_id
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
        assert self.errors is not None
        return self.errors[0]

    def is_billable_message(self) -> bool:
        """Check if this message is billable."""
        if self.conversation is None:
            return False
        return not self.conversation.is_free_conversation()

    def get_summary(self) -> dict[str, Any]:
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
            "inbox": self.inbox.get_inbox_key(),
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
