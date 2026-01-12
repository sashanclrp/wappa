"""WhatsApp API routes package."""

from .whatsapp_health import router as whatsapp_health_router
from .whatsapp_interactive import router as whatsapp_interactive_router
from .whatsapp_media import router as whatsapp_media_router
from .whatsapp_messages import router as whatsapp_messages_router
from .whatsapp_specialized import router as whatsapp_specialized_router
from .whatsapp_state_handlers import router as whatsapp_state_handlers_router
from .whatsapp_templates import router as whatsapp_templates_router

__all__ = [
    "whatsapp_health_router",
    "whatsapp_messages_router",
    "whatsapp_media_router",
    "whatsapp_interactive_router",
    "whatsapp_templates_router",
    "whatsapp_specialized_router",
    "whatsapp_state_handlers_router",
]
