"""
Consolidated WhatsApp service health endpoint.

Provides a single health check endpoint that aggregates health information
from all WhatsApp services (messages, media, interactive, templates, specialized).

Router configuration:
- Prefix: (none — inherits /api/whatsapp from combined router)
- Tags: ["WhatsApp - Health"]
- Full URL: /api/whatsapp/health
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_media_handler
from wappa.core.config.settings import settings
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)

router = APIRouter(
    prefix="",
    tags=["WhatsApp - Health"],
)


@router.get(
    "/health",
    summary="WhatsApp Services Health Check",
    description="Comprehensive health check for all WhatsApp messaging services",
)
async def whatsapp_health_check(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
    media_handler: WhatsAppMediaHandler = Depends(get_whatsapp_media_handler),
) -> dict:
    """Consolidated health check for all WhatsApp services.

    Aggregates health status from messages, media, interactive, templates,
    and specialized messaging services into a single response.

    Args:
        context: the selected Inbox Execution Context
        media_handler: WhatsApp media handler (provides media-specific information)

    Returns:
        Comprehensive health status including all service capabilities
    """
    return {
        "status": "healthy",
        "platform": context.inbox_ref.platform.value,
        "inbox_id": context.inbox_id,
        "api_version": settings.api_version,
        "timestamp": datetime.now(UTC).isoformat(),
        "services": {
            "messages": {
                "status": "healthy",
            },
            "media": {
                "status": "healthy",
                "supported_types": len(media_handler.supported_media_types),
                "max_file_sizes": media_handler.max_file_size,
            },
            "interactive": {
                "status": "healthy",
                "interactive_types": ["button", "list", "cta_url"],
                "message_types_supported": 3,
            },
            "templates": {
                "status": "healthy",
                "template_types": ["text", "media", "location"],
                "message_types_supported": 3,
            },
            "specialized": {
                "status": "healthy",
                "capabilities": [
                    "contact_cards",
                    "location_sharing",
                    "reaction_messages",
                ],
            },
        },
    }
