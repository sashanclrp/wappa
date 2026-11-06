"""Composition of Wappa's Messaging HTTP API under ``/api/{platform}``.

The Platform in the path plus ``X-Wappa-Inbox-ID`` select the Inbox. Shared
routes call that Inbox's own Messenger (one method per action, ADR-0016) or
gate on a Focused Capability (``requires_capability``), so the same route
serves every Platform and answers 501 where the Platform cannot perform it.
Routes that exist only on WhatsApp (text and media limits, validators,
Template info, ``/health``) sit behind ``whatsapp_extension_router``, whose
one router dependency answers 501 under any other Platform's path.

Shared routes are grouped by what an unauthenticated caller could *do* with
them, not by which module they live in:

- **outbound transport** — sends a message to a User
- **template transport** — sends a Template to a User
- **media management** — destroys a platform media asset
- **media upload** — creates a platform media asset
- **state handler API** — reads, overwrites, or deletes any recipient's
  cached conversational state
- **comment controls** — replies to, hides or deletes public comments
- everything else — reads: limits, lookups, downloads, health

Each group is chosen explicitly. See ADR-0007 for the outbound split and
ADR-0009 for why "mutation" had to mean more than "send".
"""

from fastapi import APIRouter, Depends

from ..dependencies.inbox_context import route_platform
from .conversations import (
    comment_controls_router,
    conversation_reads_router,
    private_reply_router,
)
from .families import MessagingRouteCapabilities, MessagingRouteProfile
from .interactive import router as interactive_info_router
from .interactive import send_router as interactive_send_router
from .media import management_router as media_management_router
from .media import router as media_router
from .media import send_router as media_send_router
from .media import upload_router as media_upload_router
from .messages import send_router as messages_send_router
from .specialized import send_router as specialized_send_router
from .state_handlers import router as state_handlers_router
from .templates import router as templates_router
from .whatsapp import whatsapp_extension_router


def resolve_capabilities(
    *,
    profile: MessagingRouteProfile | str | None = None,
    include_template_transport: bool | None = None,
    include_outbound_transport: bool | None = None,
    include_media_management: bool | None = None,
    include_media_upload: bool | None = None,
    include_state_handler_api: bool | None = None,
    include_comment_controls: bool | None = None,
) -> MessagingRouteCapabilities:
    """Turn a profile plus explicit overrides into one capability set.

    When no profile is named, ejecting outbound transport is taken as the
    signal that a Host Application owns the boundary, so the remaining
    unauthenticated mutations default off with it. Naming any capability
    explicitly always wins over both.
    """
    if profile is None:
        resolved = (
            MessagingRouteProfile.EMBEDDED
            if include_outbound_transport is False
            else MessagingRouteProfile.STANDALONE
        )
    else:
        resolved = MessagingRouteProfile(profile)

    return MessagingRouteCapabilities.for_profile(resolved).override(
        outbound_transport=include_outbound_transport,
        template_transport=include_template_transport,
        media_management=include_media_management,
        media_upload=include_media_upload,
        state_handler_api=include_state_handler_api,
        comment_controls=include_comment_controls,
    )


def create_messaging_router(
    *,
    profile: MessagingRouteProfile | str | None = None,
    include_template_transport: bool | None = None,
    include_outbound_transport: bool | None = None,
    include_media_management: bool | None = None,
    include_media_upload: bool | None = None,
    include_state_handler_api: bool | None = None,
    include_comment_controls: bool | None = None,
) -> APIRouter:
    """Compose Wappa's messaging HTTP capabilities under ``/api/{platform}``.

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
        include_comment_controls: Mount comment reply/hide/unhide/delete and
            ``comments-enabled`` (served where the Platform provides
            ``ICommentControls``).

    Every option defaults to ``None``, meaning "take it from the profile".
    """
    capabilities = resolve_capabilities(
        profile=profile,
        include_template_transport=include_template_transport,
        include_outbound_transport=include_outbound_transport,
        include_media_management=include_media_management,
        include_media_upload=include_media_upload,
        include_state_handler_api=include_state_handler_api,
        include_comment_controls=include_comment_controls,
    )

    router = APIRouter(
        prefix="/api/{platform}",
        tags=["Messaging API"],
        dependencies=[Depends(route_platform)],
        responses={
            400: {"description": "Bad Request - Invalid message format"},
            401: {"description": "Unauthorized - Invalid inbox credentials"},
            429: {"description": "Rate Limited - Too many requests"},
            500: {"description": "Internal Server Error"},
        },
    )

    # Reads and lookups: always mounted, under every profile.
    router.include_router(whatsapp_extension_router)
    router.include_router(media_router)
    router.include_router(interactive_info_router)
    router.include_router(conversation_reads_router)

    if capabilities.outbound_transport:
        router.include_router(messages_send_router)
        router.include_router(media_send_router)
        router.include_router(interactive_send_router)
        router.include_router(specialized_send_router)
        router.include_router(private_reply_router)

    if capabilities.template_transport:
        router.include_router(templates_router)

    if capabilities.media_upload:
        router.include_router(media_upload_router)

    if capabilities.media_management:
        router.include_router(media_management_router)

    if capabilities.state_handler_api:
        router.include_router(state_handlers_router)

    if capabilities.comment_controls:
        router.include_router(comment_controls_router)

    return router
