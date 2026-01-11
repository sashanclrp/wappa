"""
Wappa Core Framework Components

Provides access to core framework functionality including configuration,
logging, events, plugins, and factory system.

Clean Architecture: Core application logic and framework components.
"""

# Configuration & Settings
from .config.settings import settings

# Event System
from .events import (
    DefaultErrorHandler,
    DefaultHandlerFactory,
    DefaultMessageHandler,
    DefaultStatusHandler,
    ErrorLogStrategy,
    MessageLogStrategy,
    StatusLogStrategy,
    WappaEventDispatcher,
    WappaEventHandler,
    WebhookEndpointType,
    WebhookURLFactory,
    webhook_url_factory,
)

# Factory System
from .factory import WappaBuilder, WappaPlugin

# Logging System
from .logging import get_app_logger, get_logger, setup_app_logging

# Plugin System
from .plugins import (
    AuthPlugin,
    CORSPlugin,
    CustomMiddlewarePlugin,
    DatabasePlugin,
    RateLimitPlugin,
    RedisPlugin,
    RedisPubSubPlugin,
    WappaCorePlugin,
    WebhookPlugin,
)

# PubSub System
from .pubsub import (
    PubSubEventType,
    PubSubMessageHandler,
    PubSubMessengerWrapper,
    PubSubStatusHandler,
    publish_api_notification,
    publish_notification,
)

# Core Application
from .wappa_app import Wappa

__all__ = [
    # Configuration
    "settings",
    # Logging
    "get_logger",
    "get_app_logger",
    "setup_app_logging",
    # Event System
    "WappaEventHandler",
    "WappaEventDispatcher",
    "DefaultMessageHandler",
    "DefaultStatusHandler",
    "DefaultErrorHandler",
    "DefaultHandlerFactory",
    "MessageLogStrategy",
    "StatusLogStrategy",
    "ErrorLogStrategy",
    "WebhookURLFactory",
    "WebhookEndpointType",
    "webhook_url_factory",
    # Factory System
    "WappaBuilder",
    "WappaPlugin",
    # Plugin System
    "WappaCorePlugin",
    "AuthPlugin",
    "CORSPlugin",
    "DatabasePlugin",
    "RedisPlugin",
    "RedisPubSubPlugin",
    "RateLimitPlugin",
    "CustomMiddlewarePlugin",
    "WebhookPlugin",
    # PubSub System
    "PubSubEventType",
    "PubSubMessageHandler",
    "PubSubStatusHandler",
    "PubSubMessengerWrapper",
    "publish_notification",
    "publish_api_notification",
    # Core Application
    "Wappa",
]
