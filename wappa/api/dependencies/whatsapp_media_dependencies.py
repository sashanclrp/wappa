"""
WhatsApp media messaging dependency injection.

Provides dependency injection for WhatsApp media services including
media handlers, media messengers, and media factories.
"""

from wappa.domain.factories.media_factory import MediaFactory, WhatsAppMediaFactory

# WhatsAppMediaMessenger removed - using unified WhatsAppMessenger instead


async def get_whatsapp_media_factory() -> MediaFactory:
    """Get WhatsApp media factory.

    Returns:
        MediaFactory implementation for WhatsApp platform
    """
    return WhatsAppMediaFactory()


# get_whatsapp_media_handler moved to whatsapp_dependencies.py to eliminate duplication


# WhatsAppMediaMessenger dependency removed - using unified WhatsAppMessenger from whatsapp_dependencies.py instead
# This eliminates DRY violation and architectural redundancy
