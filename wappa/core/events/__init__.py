"""
Events module for the Wappa framework.

This module contains all event-related functionality including:
- Event handlers and processing
- Default handlers for messages, status, and errors
- Event dispatching
- Webhook URL factory
"""

from .api_event_dispatcher import APIEventDispatcher
from .default_handlers import (
    DefaultErrorHandler,
    DefaultHandlerFactory,
    DefaultMessageHandler,
    DefaultStatusHandler,
    ErrorLogStrategy,
    MessageLogStrategy,
    StatusLogStrategy,
)
from .event_dispatcher import WappaEventDispatcher
from .event_handler import WappaEventHandler
from .webhook_factory import WebhookEndpointType, WebhookURLFactory, webhook_url_factory

__all__ = [
    # Event Handlers
    "WappaEventHandler",
    "WappaEventDispatcher",
    "APIEventDispatcher",
    # Default Handlers
    "DefaultMessageHandler",
    "DefaultStatusHandler",
    "DefaultErrorHandler",
    "DefaultHandlerFactory",
    # Logging Strategies
    "MessageLogStrategy",
    "StatusLogStrategy",
    "ErrorLogStrategy",
    # Webhook Factory
    "WebhookURLFactory",
    "WebhookEndpointType",
    "webhook_url_factory",
]
