"""
Wappa - Open Source WhatsApp Business Framework

A clean, modern Python library for building WhatsApp Business applications
with minimal setup and maximum flexibility.
"""

from .core.config.settings import settings
from .core.events import (
    DefaultErrorHandler,
    DefaultHandlerFactory,
    DefaultMessageHandler,
    DefaultStatusHandler,
    ErrorLogStrategy,
    MessageLogStrategy,
    StatusLogStrategy,
    WappaEventHandler,
    WebhookURLFactory,
    webhook_url_factory,
)
from .core.wappa_app import Wappa
from .domain.interfaces.messaging_interface import IMessenger
from .messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger

__version__ = settings.version
__all__ = [
    # Core Framework
    "Wappa",
    "WappaEventHandler",
    # Webhook Management
    "WebhookURLFactory",
    "webhook_url_factory",
    # Default Handlers
    "DefaultMessageHandler",
    "DefaultStatusHandler",
    "DefaultErrorHandler",
    "DefaultHandlerFactory",
    "MessageLogStrategy",
    "StatusLogStrategy",
    "ErrorLogStrategy",
    # Messaging
    "WhatsAppMessenger",
    "IMessenger",
]
