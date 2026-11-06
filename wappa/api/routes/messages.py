"""Shared message send routes under ``/api/{platform}/messages``.

- ``POST /send-text``: text with optional reply and link preview
- ``POST /mark-as-read``: mark an inbound message read, optionally with typing

Text keeps WhatsApp's length limit; Instagram splits a longer text into
several messages.
"""

from fastapi import Depends, Request

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import get_inbox_messenger
from wappa.api.routes.families import RouteFamily
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

_family = RouteFamily(
    prefix="/messages",
    tags=["Messages"],
    responses={
        400: {"description": "Bad Request - Invalid message format"},
        401: {"description": "Unauthorized - Invalid inbox credentials"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)
send_router = _family.router()


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
