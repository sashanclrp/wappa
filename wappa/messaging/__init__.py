"""
Wappa Messaging Components

Provides access to messaging interfaces and platform-specific implementations
including WhatsApp client, messenger, and specialized handlers.

Clean Architecture: Application services and infrastructure implementations.

Usage (User Request: Quick access to WhatsApp messaging components):
    # Core messaging interface
    from wappa.messaging import IMessenger

    # WhatsApp client and messenger
    from wappa.messaging.whatsapp import WhatsAppClient, WhatsAppMessenger

    # WhatsApp specialized handlers
    from wappa.messaging.whatsapp import (
        WhatsAppMediaHandler,
        WhatsAppInteractiveHandler,
        WhatsAppTemplateHandler,
        WhatsAppSpecializedHandler
    )
"""

# Core Messaging Interface
from wappa.domain.interfaces.messaging_interface import IMessenger

# WhatsApp Client & Messenger (User Request: Quick access)
from .whatsapp.client import WhatsAppClient, WhatsAppFormDataBuilder, WhatsAppUrlBuilder

# WhatsApp Specialized Handlers (User Request: Quick access)
from .whatsapp.handlers import (
    WhatsAppInteractiveHandler,
    WhatsAppMediaHandler,
    WhatsAppSpecializedHandler,
    WhatsAppTemplateHandler,
)
from .whatsapp.messenger import WhatsAppMessenger

__all__ = [
    # Core Interface
    "IMessenger",
    # WhatsApp Client & Utilities
    "WhatsAppClient",
    "WhatsAppUrlBuilder",
    "WhatsAppFormDataBuilder",
    # WhatsApp Messenger
    "WhatsAppMessenger",
    # WhatsApp Handlers (User Request: Clean access to all handlers)
    "WhatsAppMediaHandler",
    "WhatsAppInteractiveHandler",
    "WhatsAppTemplateHandler",
    "WhatsAppSpecializedHandler",
]
