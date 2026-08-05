"""Composition of Wappa's WhatsApp HTTP capabilities.

Wappa mounts several separable things under ``/api/whatsapp``. They are grouped
by what an unauthenticated caller could *do* with them, not by which module
they live in:

- **outbound transport** — sends a message to a User
- **template transport** — sends a Template to a User
- **media management** — destroys a platform media asset
- **media upload** — creates a platform media asset
- **state handler API** — reads, overwrites, or deletes any recipient's
  cached conversational state
- everything else — reads: limits, validation, lookups, downloads, health

Each group is chosen explicitly. See ADR-0007 for the outbound split and
ADR-0009 for why "mutation" had to mean more than "send".
"""

from fastapi import APIRouter

from .whatsapp import (
    whatsapp_health_router,
    whatsapp_interactive_info_router,
    whatsapp_interactive_send_router,
    whatsapp_media_management_router,
    whatsapp_media_router,
    whatsapp_media_send_router,
    whatsapp_media_upload_router,
    whatsapp_message_info_router,
    whatsapp_messages_send_router,
    whatsapp_specialized_send_router,
    whatsapp_specialized_validation_router,
    whatsapp_state_handlers_router,
    whatsapp_template_info_router,
    whatsapp_templates_router,
)
from .whatsapp.route_families import WhatsAppRouteCapabilities, WhatsAppRouteProfile


def resolve_capabilities(
    *,
    profile: WhatsAppRouteProfile | str | None = None,
    include_template_transport: bool | None = None,
    include_outbound_transport: bool | None = None,
    include_media_management: bool | None = None,
    include_media_upload: bool | None = None,
    include_state_handler_api: bool | None = None,
) -> WhatsAppRouteCapabilities:
    """Turn a profile plus explicit overrides into one capability set.

    When no profile is named, ejecting outbound transport is taken as the
    signal that a Host Application owns the boundary, so the remaining
    unauthenticated mutations default off with it. Naming any capability
    explicitly always wins over both.
    """
    if profile is None:
        resolved = (
            WhatsAppRouteProfile.EMBEDDED
            if include_outbound_transport is False
            else WhatsAppRouteProfile.STANDALONE
        )
    else:
        resolved = WhatsAppRouteProfile(profile)

    return WhatsAppRouteCapabilities.for_profile(resolved).override(
        outbound_transport=include_outbound_transport,
        template_transport=include_template_transport,
        media_management=include_media_management,
        media_upload=include_media_upload,
        state_handler_api=include_state_handler_api,
    )


def create_whatsapp_router(
    *,
    profile: WhatsAppRouteProfile | str | None = None,
    include_template_transport: bool | None = None,
    include_outbound_transport: bool | None = None,
    include_media_management: bool | None = None,
    include_media_upload: bool | None = None,
    include_state_handler_api: bool | None = None,
) -> APIRouter:
    """Compose Wappa's WhatsApp HTTP capabilities explicitly.

    Args:
        profile: ``"standalone"`` (default) mounts everything except Template
            mutations — the surface a standalone Wappa app has always had.
            ``"embedded"`` omits every route that sends, deletes, or rewrites
            state, keeping reads, media upload, and lookups.
        include_template_transport: Mount Template mutation routes.
        include_outbound_transport: Mount ordinary send routes. Passing
            ``False`` without a profile implies the embedded profile.
        include_media_management: Mount ``DELETE /media/{id}``.
        include_media_upload: Mount ``POST /media/upload``.
        include_state_handler_api: Mount ``/state-handlers/*``.

    Every option defaults to ``None``, meaning "take it from the profile".
    """
    capabilities = resolve_capabilities(
        profile=profile,
        include_template_transport=include_template_transport,
        include_outbound_transport=include_outbound_transport,
        include_media_management=include_media_management,
        include_media_upload=include_media_upload,
        include_state_handler_api=include_state_handler_api,
    )

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

    # Reads and lookups: always mounted, under every profile.
    router.include_router(whatsapp_health_router)
    router.include_router(whatsapp_media_router)
    router.include_router(whatsapp_message_info_router)
    router.include_router(whatsapp_interactive_info_router)
    router.include_router(whatsapp_specialized_validation_router)
    router.include_router(whatsapp_template_info_router)

    if capabilities.outbound_transport:
        router.include_router(whatsapp_messages_send_router)
        router.include_router(whatsapp_media_send_router)
        router.include_router(whatsapp_interactive_send_router)
        router.include_router(whatsapp_specialized_send_router)

    if capabilities.template_transport:
        router.include_router(whatsapp_templates_router)

    if capabilities.media_upload:
        router.include_router(whatsapp_media_upload_router)

    if capabilities.media_management:
        router.include_router(whatsapp_media_management_router)

    if capabilities.state_handler_api:
        router.include_router(whatsapp_state_handlers_router)

    return router
