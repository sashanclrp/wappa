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

# Factory System
from .core.factory import WappaBuilder, WappaPlugin

# Core Plugins
from .core.plugins import (
    AuthPlugin,
    CORSPlugin,
    CustomMiddlewarePlugin,
    DatabasePlugin,
    RateLimitPlugin,
    RedisPlugin,
    WebhookPlugin,
)
from .core.wappa_app import Wappa

# Database System
from .database import DatabaseAdapter, MySQLAdapter, PostgreSQLAdapter, SQLiteAdapter

# Messaging Interface
from .domain.interfaces.messaging_interface import IMessenger
from .messaging.whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger

# Redis System
from .persistence.redis import RedisClient, RedisManager

__version__ = settings.version
__all__ = [
    # Core Framework
    "Wappa",
    "WappaEventHandler",
    # Factory System
    "WappaBuilder",
    "WappaPlugin",
    # Core Plugins
    "DatabasePlugin",
    "RedisPlugin",
    "WebhookPlugin",
    "CORSPlugin",
    "AuthPlugin",
    "RateLimitPlugin",
    "CustomMiddlewarePlugin",
    # Database Adapters
    "DatabaseAdapter",
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "MySQLAdapter",
    # Redis System
    "RedisClient",
    "RedisManager",
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
