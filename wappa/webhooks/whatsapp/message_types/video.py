"""
WhatsApp video message schema.

This module contains Pydantic models for processing WhatsApp video messages,
including video files, forwarded videos, and videos sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.webhooks.core.base_message import BaseMessageContext, BaseVideoMessage
from wappa.webhooks.core.types import (
    ConversationType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.whatsapp.base_models import AdReferral, MessageContext


class VideoContent(BaseModel):
    """Video message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    caption: str | None = Field(None, description="Video caption text (optional)")
    mime_type: str = Field(
        ..., description="MIME type of the video file (e.g., 'video/mp4')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the video file")
    id: str = Field(..., description="Media asset ID for retrieving the video file")
    url: str | None = Field(
        None,
        description="Direct download URL for the video (temporary, requires authentication)",
    )

    @field_validator("caption")
    @classmethod
    def validate_caption(cls, v: str | None) -> str | None:
        """Validate video caption if present."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if len(v) > 1024:  # WhatsApp caption limit
                raise ValueError("Video caption cannot exceed 1024 characters")
        return v

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate video MIME type format."""
        if not v.startswith("video/"):
            raise ValueError("Video MIME type must start with 'video/'")
        return v.lower()

    @field_validator("id")
    @classmethod
    def validate_media_id(cls, v: str) -> str:
        """Validate media asset ID."""
        if not v or len(v) < 10:
            raise ValueError("Media asset ID must be at least 10 characters")
        return v


class WhatsAppVideoMessage(BaseVideoMessage):
    """
    WhatsApp video message model.

    Supports various video message scenarios:
    - Regular video uploads
    - Forwarded video messages
    - Click-to-WhatsApp ad video messages
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
        ..., alias="timestamp", description="Unix timestamp when the message was sent"
    )
    type: Literal["video"] = Field(
        ..., description="Message type, always 'video' for video messages"
    )

    # Video content
    video: VideoContent = Field(..., description="Video message content and metadata")

    # Optional context fields
    context: MessageContext | None = Field(
        None, description="Context for forwards (video messages don't support replies)"
    )
    referral: AdReferral | None = Field(
        None, description="Click-to-WhatsApp ad referral information"
    )

    @property
    def sender_id(self) -> str:
        """Get the recommended sender identifier (BSUID if available, else phone)."""
        if self.from_bsuid and self.from_bsuid.strip():
            return self.from_bsuid.strip()
        return self.from_

    @property
    def has_bsuid(self) -> bool:
        """Check if this message has a BSUID set."""
        return bool(self.from_bsuid and self.from_bsuid.strip())

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
                "Message cannot have both referral (ad) and context (forward)"
            )

        # Video messages typically only support forwarding context, not replies
        if (
            self.context
            and self.context.id
            and not (self.context.forwarded or self.context.frequently_forwarded)
        ):
            raise ValueError(
                "Video messages do not support reply context, only forwarding"
            )

        return self

    @property
    def is_forwarded(self) -> bool:
        """Check if this video message was forwarded."""
        return self.context is not None and (
            self.context.forwarded or self.context.frequently_forwarded
        )

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this video message was forwarded more than 5 times."""
        return self.context is not None and self.context.frequently_forwarded is True

    @property
    def has_caption(self) -> bool:
        """Check if this video has a caption."""
        return self.video.caption is not None and len(self.video.caption.strip()) > 0

    @property
    def is_ad_message(self) -> bool:
        """Check if this video message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def media_id(self) -> str:
        """Get the media asset ID for downloading the video file."""
        return self.video.id

    @property
    def mime_type(self) -> str:
        """Get the video MIME type."""
        return self.video.mime_type

    @property
    def file_hash(self) -> str:
        """Get the SHA-256 hash of the video file."""
        return self.video.sha256

    @property
    def caption(self) -> str | None:
        """Get the video caption."""
        return self.video.caption

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    @property
    def media_type(self):
        """Get the media type from MediaType enum."""
        from wappa.webhooks.core.types import MediaType

        mime_str = self.video.mime_type
        try:
            return MediaType(mime_str)
        except ValueError:
            # Fallback for unknown video MIME types
            return MediaType.VIDEO_MP4

    @property
    def file_size(self) -> int | None:
        """Get the file size in bytes if available."""
        return None  # WhatsApp doesn't provide file size in webhooks

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp video messages.

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
            "has_caption": self.has_caption,
            "caption_length": len(self.caption) if self.caption else 0,
            "is_forwarded": self.is_forwarded,
            "is_frequently_forwarded": self.is_frequently_forwarded,
            "is_ad_message": self.is_ad_message,
        }

    # Implement abstract methods from BaseMessage
    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def message_id(self) -> str:
        return self.id

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
            "timestamp": self.timestamp,
            "processed_at": self.processed_at.isoformat(),
            "has_context": self.has_context(),
            "media_id": self.media_id,
            "media_type": self.media_type.value,
            "caption": self.caption,
            "duration": self.duration,
            "dimensions": self.dimensions,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "type": self.type,
                "video_content": self.video.model_dump(),
            },
        }

    def get_platform_data(self) -> dict[str, Any]:
        return {
            "whatsapp_message_id": self.id,
            "video_content": self.video.model_dump(),
        }

    def get_download_info(self) -> dict[str, Any]:
        """Get information needed to download the media file."""
        return {
            "media_id": self.media_id,
            "mime_type": self.media_type.value,
            "sha256": self.video.sha256,
            "platform": "whatsapp",
            "requires_auth": True,
            "download_method": "whatsapp_media_api",
        }

    # Implement abstract methods from BaseVideoMessage
    @property
    def duration(self) -> int | None:
        return None

    @property
    def dimensions(self) -> tuple[int, int] | None:
        return None

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppVideoMessage":
        return cls.model_validate(data)
