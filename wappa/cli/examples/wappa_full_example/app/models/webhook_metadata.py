"""
Webhook metadata models for different message types.

These models extract and structure relevant metadata from IncomingMessageWebhook
objects to provide comprehensive information about each message type.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Supported message types for metadata extraction."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    UNKNOWN = "unknown"


class BaseMessageMetadata(BaseModel):
    """Base metadata common to all message types."""

    message_id: str
    message_type: MessageType
    timestamp: datetime
    user_id: str
    user_name: str | None = None
    tenant_id: str
    platform: str

    # Processing metadata
    processing_time_ms: int | None = None
    cache_hit: bool = False

    class Config:
        use_enum_values = True


class TextMessageMetadata(BaseMessageMetadata):
    """Metadata specific to text messages."""

    message_type: MessageType = MessageType.TEXT
    text_content: str
    text_length: int
    has_urls: bool = False
    has_mentions: bool = False
    is_forwarded: bool = False

    @classmethod
    def from_webhook(
        cls, webhook, processing_time_ms: int = None
    ) -> "TextMessageMetadata":
        """Create TextMessageMetadata from IncomingMessageWebhook."""
        text_content = webhook.get_message_text() or ""
        return cls(
            message_id=webhook.message.message_id,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            text_content=text_content,
            text_length=len(text_content),
            has_urls="http" in text_content.lower(),
            has_mentions="@" in text_content,
            is_forwarded=webhook.was_forwarded(),
            processing_time_ms=processing_time_ms,
        )


class MediaMessageMetadata(BaseMessageMetadata):
    """Metadata specific to media messages (image, video, audio, document)."""

    media_id: str
    media_type: str
    file_size: int | None = None
    mime_type: str | None = None
    caption: str | None = None
    caption_length: int = 0
    is_forwarded: bool = False

    # Media-specific fields
    width: int | None = None
    height: int | None = None
    duration: int | None = None  # For video/audio
    filename: str | None = None  # For documents

    @classmethod
    def from_webhook(
        cls, webhook, message_type: MessageType, processing_time_ms: int = None
    ) -> "MediaMessageMetadata":
        """Create MediaMessageMetadata from IncomingMessageWebhook."""
        # Extract media information from webhook
        media_id = getattr(webhook.message, "media_id", "") or getattr(
            webhook.message, "id", ""
        )
        caption = getattr(webhook.message, "caption", "") or ""

        # Try to get additional media properties
        mime_type = getattr(webhook.message, "mime_type", None)
        file_size = getattr(webhook.message, "file_size", None)
        filename = getattr(webhook.message, "filename", None)

        # For images/videos
        width = getattr(webhook.message, "width", None)
        height = getattr(webhook.message, "height", None)
        duration = getattr(webhook.message, "duration", None)

        return cls(
            message_id=webhook.message.message_id,
            message_type=message_type,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            media_id=media_id,
            media_type=message_type.value,
            mime_type=mime_type,
            file_size=file_size,
            caption=caption,
            caption_length=len(caption),
            filename=filename,
            width=width,
            height=height,
            duration=duration,
            is_forwarded=webhook.was_forwarded(),
            processing_time_ms=processing_time_ms,
        )


class LocationMessageMetadata(BaseMessageMetadata):
    """Metadata specific to location messages."""

    message_type: MessageType = MessageType.LOCATION
    latitude: float
    longitude: float
    location_name: str | None = None
    location_address: str | None = None
    is_forwarded: bool = False

    @classmethod
    def from_webhook(
        cls, webhook, processing_time_ms: int = None
    ) -> "LocationMessageMetadata":
        """Create LocationMessageMetadata from IncomingMessageWebhook."""
        # Extract location data from webhook
        latitude = getattr(webhook.message, "latitude", 0.0)
        longitude = getattr(webhook.message, "longitude", 0.0)
        location_name = getattr(webhook.message, "name", None)
        location_address = getattr(webhook.message, "address", None)

        return cls(
            message_id=webhook.message.message_id,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            location_address=location_address,
            is_forwarded=webhook.was_forwarded(),
            processing_time_ms=processing_time_ms,
        )


class ContactMessageMetadata(BaseMessageMetadata):
    """Metadata specific to contact messages."""

    message_type: MessageType = MessageType.CONTACT
    contacts_count: int
    contact_names: list[str] = Field(default_factory=list)
    has_phone_numbers: bool = False
    has_emails: bool = False
    is_forwarded: bool = False

    @classmethod
    def from_webhook(
        cls, webhook, processing_time_ms: int = None
    ) -> "ContactMessageMetadata":
        """Create ContactMessageMetadata from IncomingMessageWebhook."""
        # Extract contact data from webhook
        contacts = getattr(webhook.message, "contacts", [])
        if not isinstance(contacts, list):
            contacts = [contacts] if contacts else []

        contact_names = []
        has_phone_numbers = False
        has_emails = False

        for contact in contacts:
            # Extract contact name
            if hasattr(contact, "name") and contact.name:
                if hasattr(contact.name, "formatted_name"):
                    contact_names.append(contact.name.formatted_name)
                else:
                    contact_names.append(str(contact.name))

            # Check for phone numbers
            if hasattr(contact, "phones") and contact.phones:
                has_phone_numbers = True

            # Check for emails
            if hasattr(contact, "emails") and contact.emails:
                has_emails = True

        return cls(
            message_id=webhook.message.message_id,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            contacts_count=len(contacts),
            contact_names=contact_names,
            has_phone_numbers=has_phone_numbers,
            has_emails=has_emails,
            is_forwarded=webhook.was_forwarded(),
            processing_time_ms=processing_time_ms,
        )


class InteractiveMessageMetadata(BaseMessageMetadata):
    """Metadata specific to interactive messages (button/list selections)."""

    message_type: MessageType = MessageType.INTERACTIVE
    interaction_type: str  # button_reply, list_reply
    selection_id: str
    selection_title: str | None = None
    context_message_id: str | None = None  # Original message that triggered this

    @classmethod
    def from_webhook(
        cls, webhook, processing_time_ms: int = None
    ) -> "InteractiveMessageMetadata":
        """Create InteractiveMessageMetadata from IncomingMessageWebhook."""
        # Extract interactive data
        selection_id = webhook.get_interactive_selection() or ""
        interaction_type = "unknown"
        selection_title = None

        # Try to determine interaction type and get more details
        if hasattr(webhook.message, "interactive") and webhook.message.interactive:
            interactive_data = webhook.message.interactive

            if hasattr(interactive_data, "type"):
                interaction_type = interactive_data.type

                # Get button reply details
                if interaction_type == "button_reply" and hasattr(
                    interactive_data, "button_reply"
                ):
                    button_reply = interactive_data.button_reply
                    selection_title = getattr(button_reply, "title", None)

                # Get list reply details
                elif interaction_type == "list_reply" and hasattr(
                    interactive_data, "list_reply"
                ):
                    list_reply = interactive_data.list_reply
                    selection_title = getattr(list_reply, "title", None)

        return cls(
            message_id=webhook.message.message_id,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            interaction_type=interaction_type,
            selection_id=selection_id,
            selection_title=selection_title,
            processing_time_ms=processing_time_ms,
        )


class UnknownMessageMetadata(BaseMessageMetadata):
    """Metadata for unsupported or unknown message types."""

    message_type: MessageType = MessageType.UNKNOWN
    raw_message_data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_webhook(
        cls, webhook, processing_time_ms: int = None
    ) -> "UnknownMessageMetadata":
        """Create UnknownMessageMetadata from IncomingMessageWebhook."""
        # Capture raw message data for debugging
        raw_data = {}
        if hasattr(webhook.message, "__dict__"):
            raw_data = {k: str(v)[:200] for k, v in webhook.message.__dict__.items()}

        return cls(
            message_id=webhook.message.message_id,
            timestamp=webhook.timestamp,
            user_id=webhook.user.user_id,
            user_name=webhook.user.profile_name,
            tenant_id=webhook.tenant.get_tenant_key(),
            platform=webhook.platform.value,
            raw_message_data=raw_data,
            processing_time_ms=processing_time_ms,
        )


# Union type for all metadata models
WebhookMetadata = (
    TextMessageMetadata
    | MediaMessageMetadata
    | LocationMessageMetadata
    | ContactMessageMetadata
    | InteractiveMessageMetadata
    | UnknownMessageMetadata
)
