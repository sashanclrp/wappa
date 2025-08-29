"""
Wappa Core Framework Components

Provides access to core framework functionality including configuration,
logging, events, plugins, and factory system.

Clean Architecture: Core application logic and framework components.
"""

# Configuration & Settings
from .config.settings import settings

# Logging System  
from .logging import get_logger, get_app_logger, setup_app_logging

# Event System
from .events import (
    WappaEventHandler,
    WappaEventDispatcher, 
    DefaultMessageHandler,
    DefaultStatusHandler,
    DefaultErrorHandler,
    DefaultHandlerFactory,
    MessageLogStrategy,
    StatusLogStrategy, 
    ErrorLogStrategy,
    WebhookURLFactory,
    WebhookEndpointType,
    webhook_url_factory,
)

# Factory System
from .factory import WappaBuilder, WappaPlugin

# Plugin System
from .plugins import (
    WappaCorePlugin,
    AuthPlugin,
    CORSPlugin,
    DatabasePlugin,
    RedisPlugin,
    RateLimitPlugin,
    CustomMiddlewarePlugin,
    WebhookPlugin,
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
    "RateLimitPlugin",
    "CustomMiddlewarePlugin",
    "WebhookPlugin",
    
    # Core Application
    "Wappa",
]
