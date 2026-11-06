"""Universal inbound-message webhook: every User-sent message on any Platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.webhook_interfaces.base_components import (
    BusinessContextBase,
    EntryReferral,
    ForwardContextBase,
    InboxBase,
    UserBase,
)


class InboundMessageWebhook(BaseModel):
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
    inbox: InboxBase = Field(description="Business inbox identification")
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
    entry_referral: EntryReferral | None = Field(
        default=None,
        description=(
            "How the User reached the conversation (ad, post, link) on every "
            "Platform, e.g. Click-to-WhatsApp or an Instagram ad"
        ),
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
            return cast(str, self.message.text_content)

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
        Get the ID of the option the User chose.

        Covers interactive replies (buttons, lists, quick replies, postbacks)
        and WhatsApp ``button`` messages, which is how Meta delivers a tap on a
        carousel card's quick reply or a Template quick-reply button
        (``button.payload``).

        Returns:
            The selected option ID/payload, or None if the User chose nothing
        """
        if self.get_message_type_name() == "button":
            return cast(str | None, getattr(self.message, "button_payload", None))
        if self.get_message_type_name() != "interactive":
            return None

        # Try to get the selected option ID from the message
        if hasattr(self.message, "selected_option_id"):
            return cast(str | None, self.message.selected_option_id)

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
                    return cast(str | None, button_reply.id)

            # Handle list replies
            elif (
                hasattr(interactive_data, "type")
                and interactive_data.type == "list_reply"
            ):
                list_reply = getattr(interactive_data, "list_reply", None)
                if list_reply and hasattr(list_reply, "id"):
                    return cast(str | None, list_reply.id)

        return None

    def has_business_context(self) -> bool:
        """Check if this message has business interaction context."""
        return self.business_context is not None

    def is_from_ad(self) -> bool:
        """Check if this message came from an ad (``entry_referral.kind``)."""
        return self.entry_referral is not None and self.entry_referral.is_ad

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

    def get_summary(self) -> dict[str, Any]:
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
            "inbox": self.inbox.get_inbox_key(),
            "has_business_context": self.has_business_context(),
            "is_from_ad": self.is_from_ad(),
            "was_forwarded": self.was_forwarded(),
            "timestamp": self.timestamp.isoformat(),
        }
