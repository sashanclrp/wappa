"""
WhatsApp audio message schema.

This module contains Pydantic models for processing WhatsApp audio messages,
including voice recordings and audio files sent via Click-to-WhatsApp ads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.schemas.core.base_message import BaseAudioMessage, BaseMessageContext
from wappa.schemas.core.types import (
    ConversationType,
    MediaType,
    PlatformType,
    UniversalMessageData,
)
from wappa.schemas.whatsapp.base_models import AdReferral, MessageContext


class AudioContent(BaseModel):
    """Audio message content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mime_type: str = Field(
        ..., description="MIME type of the audio file (e.g., 'audio/ogg; codecs=opus')"
    )
    sha256: str = Field(..., description="SHA-256 hash of the audio file")
    id: str = Field(..., description="Media asset ID for retrieving the audio file")
    voice: bool = Field(
        ..., description="True if audio is a voice recording, False if audio file"
    )

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate audio MIME type format."""
        if not v.startswith("audio/"):
            raise ValueError("Audio MIME type must start with 'audio/'")
        return v.lower()

    @field_validator("id")
    @classmethod
    def validate_media_id(cls, v: str) -> str:
        """Validate media asset ID."""
        if not v or len(v) < 10:
            raise ValueError("Media asset ID must be at least 10 characters")
        return v


class WhatsAppAudioMessage(BaseAudioMessage):
    """
    WhatsApp audio message model.

    Supports various audio message scenarios:
    - Voice recordings from WhatsApp client
    - Audio file uploads
    - Click-to-WhatsApp ad audio messages
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
    type: Literal["audio"] = Field(
        ..., description="Message type, always 'audio' for audio messages"
    )

    # Audio content
    audio: AudioContent = Field(..., description="Audio message content and metadata")

    # Optional context fields
    context: MessageContext | None = Field(
        None, description="Context for forwards (audio messages don't support replies)"
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
                "Message cannot have both referral (ad) and context (forward)"
            )

        # Audio messages typically only support forwarding context, not replies
        if (
            self.context
            and self.context.id
            and not (self.context.forwarded or self.context.frequently_forwarded)
        ):
            raise ValueError(
                "Audio messages do not support reply context, only forwarding"
            )

        return self

    @property
    def is_forwarded(self) -> bool:
        """Check if this audio message was forwarded."""
        return self.context is not None and (
            self.context.forwarded or self.context.frequently_forwarded
        )

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this audio message was forwarded more than 5 times."""
        return self.context is not None and self.context.frequently_forwarded is True

    @property
    def is_voice_recording(self) -> bool:
        """Check if this is a voice recording made with WhatsApp client."""
        return self.audio.voice

    @property
    def is_audio_file(self) -> bool:
        """Check if this is an uploaded audio file (not voice recording)."""
        return not self.audio.voice

    @property
    def is_ad_message(self) -> bool:
        """Check if this audio message came from a Click-to-WhatsApp ad."""
        return self.referral is not None

    @property
    def sender_phone(self) -> str:
        """Get the sender's phone number (clean accessor)."""
        return self.from_

    @property
    def media_id(self) -> str:
        """Get the media asset ID for downloading the audio file."""
        return self.audio.id

    @property
    def mime_type(self) -> str:
        """Get the audio MIME type."""
        return self.audio.mime_type

    @property
    def file_hash(self) -> str:
        """Get the SHA-256 hash of the audio file."""
        return self.audio.sha256

    @property
    def unix_timestamp(self) -> int:
        """Get the timestamp as an integer."""
        return self.timestamp

    def get_ad_context(self) -> tuple[str | None, str | None]:
        """
        Get ad context information for Click-to-WhatsApp audio messages.

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
            "is_voice_recording": self.is_voice_recording(),
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
            "is_voice_message": self.is_voice_message(),
            "duration": self.duration,
            "whatsapp_data": {
                "whatsapp_id": self.id,
                "from": self.from_,
                "timestamp_str": self.timestamp_str,
                "type": self.type,
                "audio_content": self.audio.model_dump(),
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
            "audio_content": self.audio.model_dump(),
            "context": self.context.model_dump() if self.context else None,
            "referral": self.referral.model_dump() if self.referral else None,
            "is_voice_recording": self.is_voice_recording(),
        }

    # Implement abstract methods from BaseMediaMessage

    @property
    def media_id(self) -> str:
        return self.audio.id

    @property
    def media_type(self) -> MediaType:
        mime_str = self.audio.mime_type
        try:
            return MediaType(mime_str)
        except ValueError:
            return MediaType.AUDIO_OGG

    @property
    def file_size(self) -> int | None:
        return None

    @property
    def caption(self) -> str | None:
        return None  # Audio messages don't have captions

    def get_download_info(self) -> dict[str, Any]:
        return {
            "media_id": self.media_id,
            "mime_type": self.media_type.value,
            "sha256": self.audio.sha256,
            "platform": "whatsapp",
            "requires_auth": True,
            "download_method": "whatsapp_media_api",
        }

    # Implement abstract methods from BaseAudioMessage

    @property
    def is_voice_message(self) -> bool:
        return self.audio.voice

    @property
    def duration(self) -> int | None:
        return None  # WhatsApp doesn't provide duration in webhooks

    @classmethod
    def from_platform_data(
        cls, data: dict[str, Any], **kwargs
    ) -> "WhatsAppAudioMessage":
        return cls.model_validate(data)
