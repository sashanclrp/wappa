"""
Wappa Data Models for API Endpoints

Re-exports WhatsApp models with cleaner import paths for creating API endpoint schemas.
This provides easy access to message models for FastAPI endpoint typing.

Clean Architecture: Domain entities and data transfer objects.

Usage (User Request: Quick access to WhatsApp models for endpoint schemas):
    # Basic message models
    from wappa.models import BasicTextMessage, MessageResult

    # Interactive models
    from wappa.models import ButtonMessage, ListMessage, CTAMessage

    # Media models
    from wappa.models import ImageMessage, VideoMessage, AudioMessage

    # Specialized models
    from wappa.models import ContactMessage, LocationMessage

    # Template models
    from wappa.models import TextTemplateMessage, MediaTemplateMessage
"""

# Re-export WhatsApp models with cleaner path (User Request: Quick access)
from ..messaging.whatsapp.models import (
    AudioMessage,
    # Basic Models
    BasicTextMessage,
    BusinessContact,
    # Interactive Models
    ButtonMessage,
    # Specialized Models
    ContactCard,
    ContactMessage,
    ContactValidationResult,
    CTAMessage,
    DocumentMessage,
    ImageMessage,
    ListMessage,
    LocationMessage,
    LocationRequestMessage,
    LocationTemplateMessage,
    LocationValidationResult,
    MediaTemplateMessage,
    # Media Models
    MediaType,
    MessageResult,
    PersonalContact,
    ReadStatusMessage,
    StickerMessage,
    TemplateMessageStatus,
    TemplateParameter,
    # Template Models
    TemplateValidationResult,
    TextTemplateMessage,
    VideoMessage,
)

__all__ = [
    # Basic Models (User Request: Clean access for endpoint schemas)
    "BasicTextMessage",
    "MessageResult",
    "ReadStatusMessage",
    # Interactive Models
    "ButtonMessage",
    "CTAMessage",
    "ListMessage",
    # Media Models
    "MediaType",
    "ImageMessage",
    "VideoMessage",
    "AudioMessage",
    "DocumentMessage",
    "StickerMessage",
    # Specialized Models
    "ContactCard",
    "ContactMessage",
    "ContactValidationResult",
    "LocationMessage",
    "LocationRequestMessage",
    "LocationValidationResult",
    "BusinessContact",
    "PersonalContact",
    # Template Models
    "TemplateParameter",
    "TextTemplateMessage",
    "MediaTemplateMessage",
    "LocationTemplateMessage",
    "TemplateMessageStatus",
    "TemplateValidationResult",
]
