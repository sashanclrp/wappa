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
    whatsapp_templates_router,
)

# Create a combined WhatsApp router
whatsapp_router = APIRouter(
    prefix="/api/whatsapp",
    tags=["WhatsApp API"],
    responses={
        400: {"description": "Bad Request - Invalid message format"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)

# Include all WhatsApp sub-routers
whatsapp_router.include_router(whatsapp_health_router)
whatsapp_router.include_router(whatsapp_messages_router)
whatsapp_router.include_router(whatsapp_media_router)
whatsapp_router.include_router(whatsapp_interactive_router)
whatsapp_router.include_router(whatsapp_templates_router)
whatsapp_router.include_router(whatsapp_specialized_router)
whatsapp_router.include_router(whatsapp_state_handlers_router)
