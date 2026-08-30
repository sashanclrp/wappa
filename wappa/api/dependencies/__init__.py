"""
FastAPI dependency injection for the Wappa WhatsApp Framework.

Provides reusable dependencies for controllers, services, and middleware
following clean architecture patterns.
"""

from .event_dependencies import dispatch_api_message_event, get_api_event_dispatcher
from .inbox_context import (
    INBOX_ID_HEADER,
    InboxExecutionContext,
    get_inbox_execution_context,
)

__all__ = [
    # Event dependencies
    "get_api_event_dispatcher",
    "dispatch_api_message_event",
    # Inbox Execution Context
    "INBOX_ID_HEADER",
    "InboxExecutionContext",
    "get_inbox_execution_context",
]
