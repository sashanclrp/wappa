"""
WhatsApp sticker message schema.

This module contains Pydantic models for processing WhatsApp sticker messages,
including animated and static stickers sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.base_message import BaseMediaMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MediaType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import AdReferral, MessageContext


class StickerContent(BaseModel):
    """Sticker message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mime_type: str = Field(
        ..., description="MIME type of the sticker file (e.g., 'image/webp')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the sticker file")
    id: str = Field(..., description="Media asset ID for retrieving the sticker file")
    animated: bool = Field(
        ..., description="True if sticker is animated, False if static"
    )

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate sticker MIME type format."""
        # Stickers are typically WebP format, but can be other image formats
        valid_types = ["image/webp", "image/png", "image/jpeg", "image/gif"]
        mime_lower = v.lower()

        if mime_lower not in valid_types:
            raise ValueError(
                f"Sticker MIME type must be one of: {', '.join(valid_types)}"
            )
        return mime_lower

    @field_validator("id")
    @classmethod
    def validate_media_id(cls, v: str) -> str:
        """Validate media asset ID."""
        if not v or len(v) < 10:
            raise ValueError("Media asset ID must be at least 10 characters")
        return v


class WhatsAppStickerMessage(BaseMediaMessage):
    """
    WhatsApp sticker message model.

    Supports various sticker message scenarios:
    - Static stickers
    - Animated stickers
    - Click-to-WhatsApp ad sticker messages
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
    type: Literal["sticker"] = Field(
        ..., description="Message type, always 'sticker' for sticker messages"
    )

    # Sticker content
    sticker: StickerContent = Field(
        ..., description="Sticker message content and metadata"
    )

    # Optional context fields
    context: MessageContext | None = Field(
        None,
        description="Context for forwards (stickers don't support replies typically)",
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

    @property
    def is_animated(self) -> bool:
        """Check if this is an animated sticker."""
        return self.sticker.animated

    @property
    def is_static(self) -> bool:
        """Check if this is a static (non-animated) sticker."""
        return not self.sticker.animated

    @property
    def is_ad_message(self) -> bool:
        """Check if this sticker message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def is_webp(self) -> bool:
        """Check if this sticker is in WebP format."""
        return self.sticker.mime_type == "image/webp"

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def media_id(self) -> str:
        """Get the media asset ID for downloading the sticker file."""
        return self.sticker.id

    @property
    def mime_type(self) -> str:
        """Get the sticker MIME type."""
        return self.sticker.mime_type

    @property
    def file_hash(self) -> str:
        """Get the SHA-256 hash of the sticker file."""
        return self.sticker.sha256

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp sticker messages.

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
            "media_id": self.media_id,
            "mime_type": self.mime_type,
            "is_animated": self.is_animated,
            "is_webp": self.is_webp,
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_type(self) -> MessageType:
        return MessageType.STICKER

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.from_

    @property
    def timestamp(self) -> int:
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .text import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
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
            "media_id": self.media_id,
            "media_type": self.media_type.value,
            "file_size": self.file_size,
            "caption": self.caption,
            "is_animated": self.is_animated,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "sticker_content": self.sticker.model_dump(),
                "context": self.context.model_dump() if self.context else None,
                "referral": self.referral.model_dump() if self.referral else None,
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "from_phone": self.from_,
            "timestamp_str": self.timestamp_str,
            "message_type": self.type,
            "sticker_content": self.sticker.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "sticker_properties": {
                "is_animated": self.is_animated,
                "is_webp": self.is_webp,
            },
        }

    # Implement abstract methods from BaseMediaMessage

    @property
    def media_id(self) -> str:
        return self.sticker.id

    @property
    def media_type(self) -> MediaType:
        mime_str = self.sticker.mime_type
        try:
            return MediaType(mime_str)
        except ValueError:
            return MediaType.IMAGE_WEBP

    @property
    def file_size(self) -> int | None:
        return None  # WhatsApp doesn't provide file size in webhooks

    @property
    def caption(self) -> str | None:
        return None  # Stickers don't have captions

    def get_download_info(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "mime_type": self.media_type.value,
            "sha256": self.sticker.sha256,
            "platform": "whatsapp",
            "requires_auth": True,
            "download_method": "whatsapp_media_api",
            "is_animated": self.is_animated,
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppStickerMessage":
        return cls.model_validate(data)
