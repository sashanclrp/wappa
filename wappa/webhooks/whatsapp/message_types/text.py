"""
WhatsApp text message schema.

This module contains Pydantic models for processing WhatsApp text messages,
including regular text, forwarded messages, message business button replies,
and Click-to-WhatsApp ad messages.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.types import (
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMessageContext, BaseTextMessage
from wappa.webhooks.whatsapp.models.base import (
    AdReferral,
    MessageContext,
)

from ._base import WhatsAppMessageBase
from .context import WhatsAppMessageContext


class TextContent(BaseModel):
    """Text message content."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    body: str = Field(
        ...,
        description="The text content of the message",
        min_length=1,
    )

    @field_validator("body")
    @classmethod
    def validate_body_not_empty(cls, v: str) -> str:
        """Validate message body is not empty or whitespace only."""
        if not v.strip():
            raise ValueError("Text message body cannot be empty")
        return v.strip()


class WhatsAppTextMessage(WhatsAppMessageBase, BaseTextMessage):
    """
    WhatsApp text message model.

    Supports various text message scenarios:
    - Regular text messages
    - Forwarded text messages
    - Message business button replies (with product context)
    - Click-to-WhatsApp ad messages

    Updated for BSUID support (v24.0+):
    - from_user_id: Business Scoped User ID (BSUID) - stable identifier
    - from_: Now optional, may be empty for username-only users
    - effective_sender_id property: Returns BSUID if available, else phone number
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields
    type: Literal["text"] = Field(
        ..., description="Message type, always 'text' for text messages"
    )

    # Text content
    text: TextContent = Field(..., description="Text message content")

    # Optional context fields
    context: MessageContext | None = Field(
        None, description="Context for replies, forwards, or message business buttons"
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @property
    def has_phone_number(self) -> bool:
        """Check if this message has a phone number (from_) set."""
        return bool(self.from_ and self.from_.strip())

    @property
    def is_username_only_sender(self) -> bool:
        """
        Check if the sender is username-only (has BSUID but no phone number visible).

        This happens when the user has enabled usernames and business hasn't
        messaged them recently or isn't in their contacts.
        """
        return self.has_bsuid and not self.has_phone_number

    @model_validator(mode="after")
    def validate_message_consistency(self) -> Self:
        """Validate message field consistency."""
        # If we have a referral, this should be from an ad
        if self.referral and self.context:
            raise ValueError(
                "Message cannot have both referral (ad) and context (reply/forward)"
            )

        # If context has forwarded flags, it should not have product info
        if (
            self.context
            and (self.context.forwarded or self.context.frequently_forwarded)
            and self.context.referred_product
        ):
            raise ValueError("Forwarded messages cannot have product referral context")

        return self

    @property
    def is_forwarded(self) -> bool:
        """Check if this message was forwarded."""
        return bool(
            self.context is not None
            and (self.context.forwarded or self.context.frequently_forwarded)
        )

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this message was forwarded more than 5 times."""
        return self.context is not None and self.context.frequently_forwarded is True

    @property
    def is_reply(self) -> bool:
        """Check if this message is a reply to another message."""
        return (
            self.context is not None
            and self.context.id is not None
            and not self.is_forwarded
            and self.context.referred_product is None
        )

    @property
    def is_business_button_reply(self) -> bool:
        """Check if this message came from a message business button."""
        return self.context is not None and self.context.referred_product is not None

    @property
    def is_ad_message(self) -> bool:
        """Check if this message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def message_body(self) -> str:
        """Get the text message body (clean accessor)."""
        return self.text.body

    def get_reply_context(self) -> tuple[str | None, str | None]:
        """
        Get reply context information.

        Returns:
            Tuple of (original_sender, original_message_id) if this is a reply,
            (None, None) otherwise.
        """
        if self.is_reply and self.context:
            return (self.context.from_, self.context.id)
        return (None, None)

    def get_product_context(self) -> tuple[str | None, str | None]:
        """
        Get product context information for message business button replies.

        Returns:
            Tuple of (catalog_id, product_id) if this came from a product button,
            (None, None) otherwise.
        """
        if (
            self.is_business_button_reply
            and self.context
            and self.context.referred_product
        ):
            product = self.context.referred_product
            return (product.catalog_id, product.product_retailer_id)
        return (None, None)

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp messages.

        Returns:
            Tuple of (ad_id, ad_click_id) if this came from an ad,
            (None, None) otherwise.
        """
        if self.is_ad_message and self.referral:
            return (self.referral.source_id, self.referral.ctwa_clid)
        return (None, None)

    def to_summary_dict(self) -> dict[str, str | bool | int]:
        """
        Create a summary dictionary for logging and analysis.

        Returns:
            Dictionary with key message information for structured logging.
        """
        return {
            "message_id": self.id,
            "sender": self.sender_phone,
            "timestamp": self.unix_timestamp,
            "type": self.type,
            "body_length": len(self.message_body),
            "is_reply": self.is_reply,
            "is_forwarded": self.is_forwarded,
            "is_frequently_forwarded": self.is_frequently_forwarded,
            "is_business_button": self.is_business_button_reply,
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage

    def has_context(self) -> bool:
        """Check if this message has context (reply, forward, etc.)."""
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        """Convert to platform-agnostic dictionary representation."""
        context = self.get_context()
        return {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "conversation_id": self.conversation_id,
            "conversation_type": self.conversation_type.value,
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "content": self.text_content,
            "text_length": len(self.text_content),
            "is_reply": self.is_reply,
            "is_forwarded": self.is_forwarded,
            "is_frequently_forwarded": self.is_frequently_forwarded,
            "context": context.to_universal_dict() if context else None,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "is_business_button_reply": self.is_business_button_reply,
                "is_ad_message": self.is_ad_message,
                "referral": self.referral.model_dump() if self.referral else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        """Get platform-specific data for advanced processing."""
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "text_content": self.text.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "is_business_button_reply": self.is_business_button_reply,
            "is_ad_message": self.is_ad_message,
            "product_context": self.get_product_context(),
            "ad_context": self.get_ad_context(),
        }

    # Implement abstract methods from BaseTextMessage

    @property
    def text_content(self) -> str:
        """Get the text content of the message."""
        return self.text.body

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppTextMessage":
        """Create message instance from WhatsApp-specific data."""
        return cls.model_validate(data)
