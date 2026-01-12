"""
WhatsApp image message schema.

This module contains Pydantic models for processing WhatsApp image messages,
including regular images, forwarded images, and Click-to-WhatsApp ad images.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.webhooks.core.base_message import BaseImageMessage, BaseMessageContext
from wappa.webhooks.core.types import (
    ConversationType,
    MediaType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import AdReferral, MessageContext


class ImageContent(BaseModel):
    """Image message content with media asset information."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(
        ..., description="Media asset ID for retrieving the image from WhatsApp"
    )
    mime_type: str = Field(
        ..., description="MIME type of the image (e.g., 'image/jpeg', 'image/png')"
    )
    sha256: str = Field(..., description="SHA256 hash of the image file")
    caption: str | None = Field(
        None,
        description="Optional image caption text",
        max_length=1024,  # WhatsApp caption limit
    )
    url: str | None = Field(
        None,
        description="Direct download URL for the image (temporary, requires authentication)",
    )

    @field_validator("id")
    @classmethod
    def validate_media_id(cls, v: str) -> str:
        """Validate media asset ID format."""
        if not v or len(v) < 10:
            raise ValueError("Media asset ID must be at least 10 characters")
        return v

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate MIME type is for images."""
        valid_image_types = [
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/bmp",
            "image/tiff",
        ]
        if v.lower() not in valid_image_types:
            raise ValueError(f"MIME type must be a valid image type, got: {v}")
        return v.lower()

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, v: str | None) -> str | None:
        """Validate caption length and content."""
        if v is not None:
            v = v.strip()
            if not v:  # Empty after stripping
                return None
            if len(v) > 1024:
                raise ValueError("Image caption cannot exceed 1024 characters")
        return v


class WhatsAppImageMessage(BaseImageMessage):
    """
    WhatsApp image message model.

    Supports various image message scenarios:
    - Regular image messages with optional captions
    - Forwarded image messages
    - Click-to-WhatsApp ad images
    """

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    # Standard message fields (BSUID support v24.0+)
    from_: str = Field(
        default="",
        alias="from",
        description="WhatsApp user phone number (may be empty for username-only users)",
    )
    from_bsuid: str | None = Field(
        None,
        alias="from_user_id",
        description="Business Scoped User ID (BSUID) - stable identifier from webhook",
    )
    id: str = Field(..., description="Unique WhatsApp message ID")
    timestamp_str: str = Field(
        ..., alias="timestamp", description="Unix timestamp when the image was sent"
    )
    type: Literal["image"] = Field(
        ..., description="Message type, always 'image' for image messages"
    )

    # Image content
    image: ImageContent = Field(
        ..., description="Image message content and media information"
    )

    # Optional context fields
    context: MessageContext | None = Field(
        None, description="Context for forwarded images (no reply context for images)"
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @property
    def sender_id(self) -> str:
        """
        Get the recommended sender identifier for caching, storage, and messaging.

        Returns:
            BSUID if available, otherwise phone number (from_).
        """
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        """Check if this message has a BSUID set."""
        return bool(self.from_bsuid and self.from_bsuid.strip())

    @property
    def has_phone_number(self) -> bool:
        """Check if this message has a phone number (from_) set."""
        return bool(self.from_ and self.from_.strip())

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
        # If we have a referral, this should be from an ad (no forwarding context)
        if (
            self.referral
            and self.context
            and (self.context.forwarded or self.context.frequently_forwarded)
        ):
            raise ValueError(
                "Ad images cannot be forwarded (cannot have both referral and forwarding context)"
            )

        # Images don't support reply context or product context
        if self.context:
            if (
                self.context.id
                and self.context.from_
                and not (self.context.forwarded or self.context.frequently_forwarded)
            ):
                raise ValueError("Images cannot be replies to other messages")

            if self.context.referred_product:
                raise ValueError("Images cannot have product referral context")

        return self

    @property
    def is_forwarded(self) -> bool:
        """Check if this image was forwarded."""
        return self.context is not None and (
            self.context.forwarded or self.context.frequently_forwarded
        )

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this image was forwarded more than 5 times."""
        return self.context is not None and self.context.frequently_forwarded is True

    @property
    def is_ad_image(self) -> bool:
        """Check if this image came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def has_caption(self) -> bool:
        """Check if this image has a caption."""
        return self.image.caption is not None and len(self.image.caption.strip()) > 0

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    @property
    def media_asset_id(self) -> str:
        """Get the media asset ID for retrieving the image."""
        return self.image.id

    @property
    def image_mime_type(self) -> str:
        """Get the image MIME type."""
        return self.image.mime_type

    @property
    def image_hash(self) -> str:
        """Get the SHA256 hash of the image."""
        return self.image.sha256

    @property
    def caption_text(self) -> str | None:
        """Get the image caption text."""
        return self.image.caption

    def get_file_extension(self) -> str:
        """
        Get the likely file extension based on MIME type.

        Returns:
            File extension including the dot (e.g., '.jpg', '.png').
        """
        mime_to_ext = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/tiff": ".tiff",
        }
        return mime_to_ext.get(self.image_mime_type, ".jpg")

    def get_suggested_filename(self) -> str:
        """
        Generate a suggested filename for the image.

        Returns:
            Suggested filename using message ID and appropriate extension.
        """
        # Use message ID (without 'wamid.' prefix) as base filename
        base_name = self.id.replace("wamid.", "").replace("=", "")[:20]
        return f"image_{base_name}{self.get_file_extension()}"

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp images.

        Returns:
            Tuple of (ad_id, ad_click_id) if this came from an ad,
            (None, None) otherwise.
        """
        if self.is_ad_image and self.referral:
            return (self.referral.source_id, self.referral.ctwa_clid)
        return (None, None)

    def to_summary_dict(self) -> dict[str, str | bool | int | None]:
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
            "media_id": self.media_asset_id,
            "mime_type": self.image_mime_type,
            "has_caption": self.has_caption,
            "caption_length": len(self.caption_text) if self.caption_text else 0,
            "is_forwarded": self.is_forwarded,
            "is_frequently_forwarded": self.is_frequently_forwarded,
            "is_ad_image": self.is_ad_image,
            "file_hash": self.image_hash,
            "suggested_filename": self.get_suggested_filename(),
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
    def timestamp(self) -> int:
        """Get the message timestamp as Unix timestamp."""
        return int(self.timestamp_str)

    @property
    def conversation_id(self) -> str:
        """Get the conversation/chat identifier."""
        return self.from_

    @property
    def conversation_type(self) -> ConversationType:
        """Get the type of conversation."""
        return ConversationType.PRIVATE

    def has_context(self) -> bool:
        """Check if this message has context."""
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        """Get message context if available."""
        from .text import WhatsAppMessageContext

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
            "media_id": self.media_id,
            "media_type": self.media_type.value,
            "file_size": self.file_size,
            "caption": self.caption,
            "has_caption": self.has_caption(),
            "is_forwarded": self.is_forwarded,
            "context": (
                self.get_context().to_universal_dict() if self.has_context() else None
            ),
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "image_content": self.image.model_dump(),
                "context": self.context.model_dump() if self.context else None,
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
            "image_content": self.image.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "is_ad_image": self.is_ad_image,
            "suggested_filename": self.get_suggested_filename(),
        }

    # Implement abstract methods from BaseMediaMessage

    @property
    def media_id(self) -> str:
        """Get the platform-specific media identifier."""
        return self.image.id

    @property
    def media_type(self) -> MediaType:
        """Get the media MIME type."""
        mime_str = self.image.mime_type
        try:
            return MediaType(mime_str)
        except ValueError:
            # Fallback for unknown MIME types
            return MediaType.IMAGE_JPEG

    @property
    def file_size(self) -> int | None:
        """Get the file size in bytes if available."""
        return None  # WhatsApp doesn't provide file size in webhooks

    @property
    def caption(self) -> str | None:
        """Get the media caption/description if available."""
        return self.image.caption

    def get_download_info(self) -> dict[str, Any]:
        """Get information needed to download the media file."""
        return {
            "media_id": self.media_id,
            "mime_type": self.media_type.value,
            "sha256": self.image.sha256,
            "platform": "whatsapp",
            "requires_auth": True,
            "download_method": "whatsapp_media_api",
        }

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppImageMessage":
        """Create message instance from WhatsApp-specific data."""
        return cls.model_validate(data)
