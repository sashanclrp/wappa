"""
WhatsApp text message schema.

This module contains Pydantic models for processing WhatsApp text messages,
including regular text, forwarded messages, message business button replies,
and Click-to-WhatsApp ad messages.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.base_message import BaseMessageContext, BaseTextMessage
from wappa.schemas.core.types import (
    ConversationType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import AdReferral, MessageContext


class TextContent(BaseModel):
    """Text message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(
        ...,
        description="The text content of the message",
        min_length=1,
        max_length=4096,  # WhatsApp text message limit
    )

    @field_validator("body")
    @classmethod
    def validate_body_not_empty(cls, v: str) -> str:
        """Validate message body is not empty or whitespace only."""
        if not v.strip():
            raise ValueError("Text message body cannot be empty")
        return v.strip()


class WhatsAppMessageContext(BaseMessageContext):
    """
    WhatsApp-specific message context adapter for universal interface.

    Adapts WhatsApp MessageContext to the universal context interface.
    """

    def __init__(self, whatsapp_context: MessageContext | None):
        super().__init__()
        self._context = whatsapp_context

    @property
    def original_message_id(self) -> str | None:
        """Get the ID of the original message being replied to or forwarded."""
        return self._context.id if self._context else None

    @property
    def original_sender_id(self) -> str | None:
        """Get the sender ID of the original message."""
        return self._context.from_ if self._context else None

    @property
    def is_reply(self) -> bool:
        """Check if this represents a reply context."""
        if not self._context:
            return False
        return (
            self._context.id is not None
            and not self._context.forwarded
            and not self._context.frequently_forwarded
            and self._context.referred_product is None
        )

    @property
    def is_forward(self) -> bool:
        """Check if this represents a forward context."""
        if not self._context:
            return False
        return self._context.forwarded or self._context.frequently_forwarded

    def to_universal_dict(self) -> dict[str, Any]:
        """Convert to platform-agnostic dictionary representation."""
        if not self._context:
            return {"platform": PlatformType.WHATSAPP.value, "has_context": False}

        return {
            "platform": PlatformType.WHATSAPP.value,
            "has_context": True,
            "original_message_id": self.original_message_id,
            "original_sender_id": self.original_sender_id,
            "is_reply": self.is_reply,
            "is_forward": self.is_forward,
            "whatsapp_data": {
                "forwarded": self._context.forwarded,
                "frequently_forwarded": self._context.frequently_forwarded,
                "referred_product": self._context.referred_product.model_dump()
                if self._context.referred_product
                else None,
            },
        }


class WhatsAppTextMessage(BaseTextMessage):
    """
    WhatsApp text message model.

    Supports various text message scenarios:
    - Regular text messages
    - Forwarded text messages
    - Message business button replies (with product context)
    - Click-to-WhatsApp ad messages
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields
    from_: str = Field(
        ..., alias="from", description="WhatsApp user phone number who sent the message"
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
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

    @field_validator("from_")
    @classmethod
    def validate_from_phone(cls, v: str) -> str:
        """Validate sender phone number format."""
        if not v or len(v) < 8:
            raise ValueError("Sender phone number must be at least 8 characters")
        # Remove common prefixes and validate numeric
        phone = v.replace("+", "").replace("-", "").replace(" ", "")
        if not phone.isdigit():
            raise ValueError("Phone number must contain only digits (and +)")
        return v

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        """Validate WhatsApp message ID format."""
        if not v or len(v) < 10:
            raise ValueError("WhatsApp message ID must be at least 10 characters")
        # WhatsApp message IDs typically start with 'wamid.'
        if not v.startswith("wamid."):
            raise ValueError("WhatsApp message ID should start with 'wamid.'")
        return v

    @field_validator("timestamp_str")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate Unix timestamp format."""
        if not v.isdigit():
            raise ValueError("Timestamp must be numeric")
        # Validate reasonable timestamp range (after 2020, before 2100)
        timestamp_int = int(v)
        if timestamp_int < 1577836800 or timestamp_int > 4102444800:
            raise ValueError("Timestamp must be a valid Unix timestamp")
        return v

    @model_validator(mode="after")
    def validate_message_consistency(self):
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
        return self.context is not None and (
            self.context.forwarded or self.context.frequently_forwarded
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
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def message_body(self) -> str:
        """Get the text message body (clean accessor)."""
        return self.text.body

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

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

    @property
    def platform(self) -> PlatformType:
        """Get the platform this message came from."""
        return PlatformType.WHATSAPP

    @property
    def message_id(self) -> str:
        """Get the unique message identifier."""
        return self.id

    @property
    def sender_id(self) -> str:
        """Get the sender's universal identifier."""
        return self.from_

    @property
    def timestamp(self) -> int:
        """Get the message timestamp as Unix timestamp."""
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        # For WhatsApp, use sender ID as conversation ID for 1-on-1 chats
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        """Get the type of conversation."""
        return ConversationType.PRIVATE  # WhatsApp messages are typically private

    def has_context(self) -> bool:
        """Check if this message has context (reply, forward, etc.)."""
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        """Convert to platform-agnostic dictionary representation."""
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
            "context": self.get_context().to_universal_dict()
            if self.has_context()
            else None,
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

    def get_reply_context(self) -> tuple[str | None, str | None]:
        """Get reply context information."""
        if self.is_reply and self.context:
            return (self.context.from_, self.context.id)
        return (None, None)

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppTextMessage":
        """Create message instance from WhatsApp-specific data."""
        return cls.model_validate(data)
