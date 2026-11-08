"""
WhatsApp sticker message schema.

This module contains Pydantic models for processing WhatsApp sticker messages,
including animated and static stickers sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.types import (
    MediaType,
    MessageType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import BaseMediaMessage, BaseMessageContext
from wappa.webhooks.whatsapp.models.base import (
    AdReferral,
    MessageContext,
)

from ._base import WhatsAppMessageBase


class StickerContent(BaseModel):
    """Sticker message content."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    mime_type: str = Field(
        ..., description="MIME type of the sticker file (e.g., 'image/webp')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the sticker file")
    id: str = Field(..., description="Media asset ID for retrieving the sticker file")
    animated: bool = Field(
        ..., description="True if sticker is animated, False if static"
    )
    url: str | None = Field(
        None,
        description="Direct download URL for the sticker (temporary, requires authentication)",
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


class WhatsAppStickerMessage(WhatsAppMessageBase, BaseMediaMessage):
    """
    WhatsApp sticker message model.

    Supports various sticker message scenarios:
    - Static stickers
    - Animated stickers
    - Click-to-WhatsApp ad sticker messages
    """

    model_config = ConfigDict(
        extra="allow", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
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
    def message_type(self) -> MessageType:
        return MessageType.STICKER

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        from .context import WhatsAppMessageContext

        return WhatsAppMessageContext(self.context) if self.context else None

    def to_universal_dict(self) -> UniversalMessageData:
        from wappa.webhooks.core.base_message.projections import media_projection

        return media_projection(self)

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

    # Abstract methods already implemented above

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
        cls, data: dict[str, Any], **kwargs: Any
    ) -> "WhatsAppStickerMessage":
        return cls.model_validate(data)
