"""
WhatsApp messaging API endpoints.

Provides REST API endpoints for WhatsApp messaging operations:
- POST /api/whatsapp/messages/send-text: Send text messages
- POST /api/whatsapp/messages/mark-as-read: Mark messages as read with optional typing

Router configuration:
- Prefix: /messages
- Tags: ["WhatsApp - Messages"]
- Full URL: /api/whatsapp/messages/
"""

from fastapi import Depends, Request

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import get_inbox_messenger
from wappa.api.dependencies.whatsapp_dependencies import (
    get_whatsapp_message_payloads,
)
from wappa.api.routes.whatsapp.route_families import RouteFamily
from wappa.api.utils import (
    direct_target,
    dispatch_message_event,
    map_send_errors,
)
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.models.basic_models import (
    BasicTextMessage,
    ReadStatusMessage,
)
from wappa.messaging.whatsapp.payload_builders import WhatsAppMessagePayloadBuilder

# Outbound mutations (`send_router`) are omissible; message limits are not.
_family = RouteFamily(
    prefix="/messages",
    tags=["WhatsApp - Messages"],
    responses={
        400: {"description": "Bad Request - Invalid message format"},
        401: {"description": "Unauthorized - Invalid inbox credentials"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)
send_router = _family.router()
router = _family.router()


@send_router.post(
    "/send-text",
    response_model=MessageResult,
    summary="Send Text Message",
    description=(
        "Send a text message with optional reply and preview control. A failed "
        "result answers its mapped 4xx status (default 400)."
    ),
)
@map_send_errors("send text message")
@dispatch_message_event()
async def send_text_message(
    request: BasicTextMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send text to the request's User on the path Inbox."""
    return await messenger.send_text(
        text=request.text,
        target=direct_target(messenger, request),
        reply_to_message_id=request.reply_to_message_id,
        disable_preview=request.disable_preview,
    )


@send_router.post(
    "/mark-as-read",
    response_model=MessageResult,
    summary="Mark Message as Read",
    description=(
        "Mark a message as read with an optional typing indicator. A failed "
        "result answers its mapped 4xx status (default 400)."
    ),
)
@map_send_errors("mark message as read")
async def mark_message_as_read(
    request: ReadStatusMessage, messenger: IMessenger = Depends(get_inbox_messenger)
) -> MessageResult:
    """Acknowledge the User's inbound message, optionally showing typing."""
    return await messenger.mark_as_read(
        request.message_id,
        direct_target(messenger, request),
        typing=request.typing,
    )


@router.get(
    "/limits",
    summary="Get Text Message Limits",
    description="Get WhatsApp text message limits. Other limits at separate endpoints.",
)
async def get_message_limits(
    payloads: WhatsAppMessagePayloadBuilder = Depends(get_whatsapp_message_payloads),
) -> dict:
    """Get WhatsApp text message limits.

    Returns current WhatsApp Business API limits for text message validation.
    This endpoint follows Single Responsibility Principle - returns only text limits.

    For other domain limits, use:
    - /api/whatsapp/media/limits for media limits
    - /api/whatsapp/interactive/limits for button/list/CTA limits
    - /api/whatsapp/templates/limits for template limits

    Args:
        payloads: WhatsApp text payload builder (injected)

    Returns:
        Dictionary containing text message limits (max_text_length, etc.)
    """
    return payloads.get_message_limits()
