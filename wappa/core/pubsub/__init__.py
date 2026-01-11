"""
PubSub notification wrappers and utilities.

This module provides wrappers that add Redis PubSub notification behavior
to various components (event handlers, messengers, etc.).

Event Types:
- incoming_message: User messages received via webhook
- outgoing_message: Messages sent via API routes
- bot_reply: Messages sent by bot via self.messenger
- status_change: Delivery/read status updates

Components:
- handlers: Wrappers for event handlers that publish notifications
- messenger_wrapper: Wrapper for IMessenger that publishes bot_reply notifications
"""

from ...domain.interfaces.pubsub_interface import PubSubEventType
from .handlers import (
    PubSubMessageHandler,
    PubSubStatusHandler,
    publish_api_notification,
    publish_notification,
)
from .messenger_wrapper import PubSubMessengerWrapper

__all__ = [
    # Event type
    "PubSubEventType",
    # Handler wrappers
    "PubSubMessageHandler",
    "PubSubStatusHandler",
    # Publisher utilities
    "publish_notification",
    "publish_api_notification",
    # Messenger wrapper
    "PubSubMessengerWrapper",
]
