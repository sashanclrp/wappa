"""WhatsApp API routes package.

Modules that mix outbound mutations with read/upload infrastructure export two
routers: ``*_send_router`` for the mutations an embedding host omits, and the
plain ``*_router`` for what stays mounted either way.
"""

from .whatsapp_health import router as whatsapp_health_router
from .whatsapp_interactive import router as whatsapp_interactive_info_router
from .whatsapp_interactive import send_router as whatsapp_interactive_send_router
from .whatsapp_media import router as whatsapp_media_router
from .whatsapp_media import send_router as whatsapp_media_send_router
from .whatsapp_messages import router as whatsapp_message_info_router
from .whatsapp_messages import send_router as whatsapp_messages_send_router
from .whatsapp_specialized import router as whatsapp_specialized_validation_router
from .whatsapp_specialized import send_router as whatsapp_specialized_send_router
from .whatsapp_state_handlers import router as whatsapp_state_handlers_router
from .whatsapp_template_info import router as whatsapp_template_info_router
from .whatsapp_templates import router as whatsapp_templates_router

__all__ = [
    "whatsapp_health_router",
    "whatsapp_interactive_info_router",
    "whatsapp_interactive_send_router",
    "whatsapp_media_router",
    "whatsapp_media_send_router",
    "whatsapp_message_info_router",
    "whatsapp_messages_send_router",
    "whatsapp_specialized_send_router",
    "whatsapp_specialized_validation_router",
    "whatsapp_state_handlers_router",
    "whatsapp_template_info_router",
    "whatsapp_templates_router",
]
