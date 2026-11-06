"""
Default event handlers for message, status and error webhooks.

Provides built-in handlers for incoming messages, status updates and error webhooks that can be
used out-of-the-box or extended by users for custom behavior.
"""

from __future__ import annotations

from ._stats import ErrorLogStrategy, LogLevel, MessageLogStrategy, StatusLogStrategy
from .conversation import DefaultConversationEventHandler
from .error import DefaultErrorHandler
from .message import DefaultMessageHandler
from .status import DefaultStatusHandler
from .system import DefaultSystemHandler

__all__ = [
    "DefaultConversationEventHandler",
    "DefaultErrorHandler",
    "DefaultMessageHandler",
    "DefaultStatusHandler",
    "DefaultSystemHandler",
    "ErrorLogStrategy",
    "LogLevel",
    "MessageLogStrategy",
    "StatusLogStrategy",
]
