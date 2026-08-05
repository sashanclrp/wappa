"""WhatsApp API routes package.

Modules holding more than one capability group export one router per group:
``*_send_router`` sends, ``*_management_router`` destroys, ``*_upload_router``
creates, and the plain ``*_router`` reads. ``whatsapp_combined`` decides which
groups get mounted — see ADR-0009.
"""

from .whatsapp_health import router as whatsapp_health_router
from .whatsapp_interactive import router as whatsapp_interactive_info_router
from .whatsapp_interactive import send_router as whatsapp_interactive_send_router
from .whatsapp_media import management_router as whatsapp_media_management_router
from .whatsapp_media import router as whatsapp_media_router
from .whatsapp_media import send_router as whatsapp_media_send_router
from .whatsapp_media import upload_router as whatsapp_media_upload_router
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
    "whatsapp_media_management_router",
    "whatsapp_media_router",
    "whatsapp_media_send_router",
    "whatsapp_media_upload_router",
    "whatsapp_message_info_router",
    "whatsapp_messages_send_router",
    "whatsapp_specialized_send_router",
    "whatsapp_specialized_validation_router",
    "whatsapp_state_handlers_router",
    "whatsapp_template_info_router",
    "whatsapp_templates_router",
]
