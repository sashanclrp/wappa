"""
Pydantic models for Redis cache conversation storage.

These models store active conversation data in Redis cache before persisting to PostgreSQL.
Supports text and media messages (images, audio, video, documents) with full metadata.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _get_utc_isoformat() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()


class CachedMessage(BaseModel):
    """
    Single message in Redis cache.

    Lightweight representation for fast access and serialization.
    Supports text and media messages (images, audio, video, documents).
    """

    message_id: str = Field(..., description="Unique message identifier")
    actor: str = Field(..., description="Message actor: user or agent")
    kind: str = Field(..., description="Message kind: text, image, audio, video, etc.")

    # Text content
    text_content: str | None = Field(None, description="Text message content")

    # Platform metadata
    platform_message_id: str | None = Field(
        None, description="Platform-specific message ID"
    )
    platform_timestamp: str | None = Field(
        None, description="Platform timestamp in ISO format"
    )

    # Media fields (for images, audio, video, documents)
    media_mime: str | None = Field(
        None, description="Media MIME type (e.g., image/jpeg, audio/ogg)"
    )
    media_sha256: str | None = Field(None, description="Media file SHA256 hash")
    media_url: str | None = Field(None, description="Media file URL or path")
    media_caption: str | None = Field(None, description="Media caption text")
    media_description: str | None = Field(
        None, description="Media description or alt text"
    )
    media_transcript: str | None = Field(None, description="Audio/video transcript")

    # JSON content (for structured data, interactive messages, etc.)
    json_content: dict | None = Field(None, description="Structured JSON content")

    created_at: str = Field(
        default_factory=_get_utc_isoformat,
        description="Creation timestamp",
    )


class ConversationCache(BaseModel):
    """
    Conversation metadata stored in Redis cache.

    Tracks active conversation state before persisting to PostgreSQL.
    """

    conversation_id: str = Field(..., description="Unique conversation identifier")
    chat_id: str = Field(..., description="Chat/user identifier")
    started_at: str = Field(
        default_factory=_get_utc_isoformat,
        description="Conversation start time",
    )
    last_activity_at: str = Field(
        default_factory=_get_utc_isoformat,
        description="Last activity timestamp",
    )
    messages: list[CachedMessage] = Field(
        default_factory=list, description="List of cached messages"
    )

    def add_message(self, message: CachedMessage) -> None:
        """Add message to conversation."""
        self.messages.append(message)
        self.last_activity_at = datetime.now(UTC).isoformat()

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)


__all__ = [
    "CachedMessage",
    "ConversationCache",
]
