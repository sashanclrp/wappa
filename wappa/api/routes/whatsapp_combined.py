"""Composition of Wappa's WhatsApp HTTP capabilities.

Wappa mounts three separable things under ``/api/whatsapp``: outbound
mutations that send something to a User, Template mutations, and the service
routes (media upload/download/lookup, limits, validation, Template info, state
handlers, health) that a Host Application needs whether or not it lets Wappa
own sending. Each is chosen explicitly here.
"""

from fastapi import APIRouter

from .whatsapp import (
    whatsapp_health_router,
    whatsapp_interactive_info_router,
    whatsapp_interactive_send_router,
    whatsapp_media_router,
    whatsapp_media_send_router,
    whatsapp_message_info_router,
    whatsapp_messages_send_router,
    whatsapp_specialized_send_router,
    whatsapp_specialized_validation_router,
    whatsapp_state_handlers_router,
    whatsapp_template_info_router,
    whatsapp_templates_router,
)


def create_whatsapp_router(
    *,
    include_template_transport: bool = False,
    include_outbound_transport: bool = True,
) -> APIRouter:
    """Compose Wappa's WhatsApp HTTP capabilities explicitly.

    Args:
        include_template_transport: Mount Wappa's Template mutation routes.
            Off by default, so an embedding host never inherits them.
        include_outbound_transport: Mount Wappa's ordinary outbound mutation
            routes — text, media sends, interactive, contact, location, and
            mark-as-read. On by default, which is what a standalone Wappa
            application has always had. An embedding host that owns its own
            authenticated send boundary turns this off; it keeps media
            upload/download/lookup, limits, validation, Template info, state
            handlers, and health, and it keeps every ``wappa.messaging``
            service, because none of those depend on this HTTP surface.
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

    # Service capabilities: always mounted.
    router.include_router(whatsapp_health_router)
    router.include_router(whatsapp_media_router)
    router.include_router(whatsapp_message_info_router)
    router.include_router(whatsapp_interactive_info_router)
    router.include_router(whatsapp_specialized_validation_router)
    router.include_router(whatsapp_template_info_router)
    router.include_router(whatsapp_state_handlers_router)

    if include_outbound_transport:
        router.include_router(whatsapp_messages_send_router)
        router.include_router(whatsapp_media_send_router)
        router.include_router(whatsapp_interactive_send_router)
        router.include_router(whatsapp_specialized_send_router)

    if include_template_transport:
        router.include_router(whatsapp_templates_router)

    return router
