"""
FastAPI dependency injection for the Wappa WhatsApp Framework.

Provides reusable dependencies for controllers, services, and middleware
following clean architecture patterns.
"""

# Import existing dependencies
from .event_dependencies import dispatch_api_message_event, get_api_event_dispatcher
from .whatsapp_dependencies import *
from .whatsapp_media_dependencies import *

__all__ = [
    # Event dependencies
    "get_api_event_dispatcher",
    "dispatch_api_message_event",
]
