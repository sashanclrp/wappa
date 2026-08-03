"""
Combined WhatsApp API router that includes all WhatsApp endpoints.

This module combines all WhatsApp API endpoints into a single router for easy inclusion
in the main Wappa application.
"""

from fastapi import APIRouter

from .whatsapp import (
    whatsapp_health_router,
    whatsapp_interactive_router,
    whatsapp_media_router,
    whatsapp_messages_router,
    whatsapp_specialized_router,
    whatsapp_state_handlers_router,
    whatsapp_template_info_router,
    whatsapp_templates_router,
)


def create_whatsapp_router(*, include_template_transport: bool = False) -> APIRouter:
    """Compose Wappa's WhatsApp HTTP capabilities explicitly.

    Template mutation routes are excluded by default. A standalone Wappa host
    must opt into them; embedding hosts therefore do not inherit an accidental
    outbound mutation surface.
    """
    router = APIRouter(
        prefix="/api/whatsapp",
        tags=["WhatsApp API"],
        responses={
            400: {"description": "Bad Request - Invalid message format"},
            401: {"description": "Unauthorized - Invalid inbox credentials"},
            429: {"description": "Rate Limited - Too many requests"},
            500: {"description": "Internal Server Error"},
        },
    )
    router.include_router(whatsapp_health_router)
    router.include_router(whatsapp_messages_router)
    router.include_router(whatsapp_media_router)
    router.include_router(whatsapp_interactive_router)
    if include_template_transport:
        router.include_router(whatsapp_templates_router)
    router.include_router(whatsapp_template_info_router)
    router.include_router(whatsapp_specialized_router)
    router.include_router(whatsapp_state_handlers_router)
    return router
