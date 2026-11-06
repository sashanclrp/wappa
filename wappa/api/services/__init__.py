"""
API services module.

Provides business logic services for API routes. The WhatsApp Template state
service lives with the WhatsApp extension in ``wappa.messaging.whatsapp.capabilities.templates``.
"""

from .handler_state_service import HandlerStateService

__all__ = ["HandlerStateService"]
