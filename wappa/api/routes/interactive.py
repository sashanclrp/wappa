"""Shared interactive routes under ``/api/{platform}/interactive``.

- ``POST /send-buttons``, ``/send-list``, ``/send-cta``, ``/send-carousel``
- ``GET /limits``: the interactive limits Wappa enforces at construction, each
  the most restrictive across the installed Platforms, so it is the same on
  every Platform path
"""

from typing import Self

from fastapi import Depends, Request
from pydantic import Field, model_validator

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import get_inbox_messenger
from wappa.api.routes.families import RouteFamily
from wappa.api.utils import (
    direct_target,
    dispatch_message_event,
    map_send_errors,
)
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interactive import (
    BUTTON_BODY_MAX,
    BUTTON_ID_MAX,
    BUTTON_TITLE_MAX,
    BUTTONS_MAX,
    CARD_BUTTONS_MAX,
    CARD_SUBTITLE_MAX,
    CARD_TEXT_MAX,
    CARD_TITLE_MAX,
    CAROUSEL_BODY_MAX,
    CAROUSEL_CARDS_MAX,
    CAROUSEL_CARDS_MIN,
    FOOTER_MAX,
    HEADER_TEXT_MAX,
    LIST_BODY_MAX,
    LIST_BUTTON_TEXT_MAX,
    LIST_ROWS_MAX,
    LIST_SECTIONS_MAX,
    ROW_DESCRIPTION_MAX,
    ROW_ID_MAX,
    ROW_TITLE_MAX,
    SECTION_TITLE_MAX,
    MessageCard,
    check_carousel,
)
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.results import MessageResult
from wappa.schemas.core.recipient import DeliveryRequest
from wappa.schemas.requests.interactive_models import (
    ButtonMessage,
    CTAMessage,
    ListMessage,
)

# Interactive sends are omissible outbound mutations; the limits endpoint
# is a read an embedding host still uses for admission checks.
_family = RouteFamily(
    prefix="/interactive",
    tags=["Interactive"],
    responses={
        400: {"description": "Bad Request - Invalid interactive message format"},
        401: {"description": "Unauthorized - Invalid inbox credentials"},
        404: {"description": "Not Found - Recipient or resource not found"},
        413: {"description": "Payload Too Large - Interactive content too large"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)
send_router = _family.router()
router = _family.router()


@send_router.post(
    "/send-buttons",
    response_model=MessageResult,
    summary="Send Button Message",
    description="Send an interactive button message with up to 3 quick reply buttons",
)
@map_send_errors("send button message")
@dispatch_message_event()
async def send_button_message(
    request: ButtonMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive button message via WhatsApp.

    1–3 reply buttons, an optional text, image, video or document header and
    an optional footer; limits are the shared minimum across Platforms.
    """
    return await messenger.send_button_message(
        buttons=request.buttons,
        target=direct_target(messenger, request),
        body=request.body,
        header=request.header,
        footer=request.footer,
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post(
    "/send-list",
    response_model=MessageResult,
    summary="Send List Message",
    description="Send an interactive list message with sectioned rows",
)
@map_send_errors("send list message")
@dispatch_message_event()
async def send_list_message(
    request: ListMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive list message via WhatsApp.

    Up to 10 sections and 10 rows in total; limits are the shared minimum
    across Platforms.
    """
    return await messenger.send_list_message(
        sections=request.sections,
        target=direct_target(messenger, request),
        body=request.body,
        button_text=request.button_text,
        header=request.header,
        footer=request.footer,
        reply_to_message_id=request.reply_to_message_id,
    )


@send_router.post(
    "/send-cta",
    response_model=MessageResult,
    summary="Send Call-to-Action Message",
    description="Send an interactive call-to-action message with URL button",
)
@map_send_errors("send CTA message")
@dispatch_message_event()
async def send_cta_message(
    request: CTAMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send a call-to-action message with one URL button.

    An optional text, image, video or document header and an optional footer;
    limits are the shared minimum across Platforms.
    """
    return await messenger.send_cta_message(
        button_text=request.button_text,
        button_url=request.button_url,
        target=direct_target(messenger, request),
        body=request.body,
        header=request.header,
        footer=request.footer,
        reply_to_message_id=request.reply_to_message_id,
    )


class CarouselMessage(DeliveryRequest):
    """A carousel of 2–10 cards (``IMessenger.send_carousel``)."""

    body: str = Field(
        ...,
        min_length=1,
        max_length=CAROUSEL_BODY_MAX,
        description="Text shown with the carousel",
    )
    cards: list[MessageCard] = Field(
        ..., min_length=CAROUSEL_CARDS_MIN, max_length=CAROUSEL_CARDS_MAX
    )
    reply_to_message_id: str | None = Field(
        None, description="Optional message ID for replies"
    )

    @model_validator(mode="after")
    def _shared_limits(self) -> Self:
        check_carousel(self.cards, self.body)
        return self


@send_router.post(
    "/send-carousel",
    response_model=MessageResult,
    summary="Send Carousel",
    description=(
        "Send a card carousel of 2–10 cards. WhatsApp: media carousel; every "
        "card needs a `header` image or video by public `url` and the same "
        "button kind and count. Instagram: generic template carousel; a video "
        "card needs `header.poster_url` (else 501). "
        "Platform rules are checked before any call."
    ),
)
@map_send_errors("send carousel")
@dispatch_message_event("carousel")
async def send_carousel_message(
    request: CarouselMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    return await messenger.send_carousel(
        request.cards,
        direct_target(messenger, request),
        request.body,
        reply_to_message_id=request.reply_to_message_id,
    )


@router.get(
    "/limits",
    summary="Get Interactive Message Limits",
    description="Get platform-specific interactive message limits and constraints",
)
async def get_interactive_limits() -> dict:
    """The interactive limits Wappa enforces before any Platform call.

    Each limit is the most restrictive one across the installed Platforms, so a
    message within them is deliverable on WhatsApp and Instagram alike.
    """
    return {
        "button_messages": {
            "min_buttons": 1,
            "max_buttons": BUTTONS_MAX,
            "max_button_title_length": BUTTON_TITLE_MAX,
            "max_button_id_length": BUTTON_ID_MAX,
            "max_body_length": BUTTON_BODY_MAX,
            "max_header_text_length": HEADER_TEXT_MAX,
            "max_footer_length": FOOTER_MAX,
            "supported_header_kinds": ["text", "image", "video", "document"],
        },
        "list_messages": {
            "max_sections": LIST_SECTIONS_MAX,
            "max_rows_total": LIST_ROWS_MAX,
            "section_title_required_when_several_sections": True,
            "row_ids_unique_across_sections": True,
            "max_button_text_length": LIST_BUTTON_TEXT_MAX,
            "max_body_length": LIST_BODY_MAX,
            "max_header_length": HEADER_TEXT_MAX,
            "max_footer_length": FOOTER_MAX,
            "max_section_title_length": SECTION_TITLE_MAX,
            "max_row_title_length": ROW_TITLE_MAX,
            "max_row_description_length": ROW_DESCRIPTION_MAX,
            "max_row_id_length": ROW_ID_MAX,
        },
        "cta_messages": {
            "max_button_text_length": BUTTON_TITLE_MAX,
            "max_body_length": BUTTON_BODY_MAX,
            "max_header_text_length": HEADER_TEXT_MAX,
            "max_footer_length": FOOTER_MAX,
            "supported_header_kinds": ["text", "image", "video", "document"],
            "required_url_protocols": ["http://", "https://"],
        },
        "carousels": {
            "min_cards": CAROUSEL_CARDS_MIN,
            "max_cards": CAROUSEL_CARDS_MAX,
            "max_body_length": CAROUSEL_BODY_MAX,
            "max_card_title_length": CARD_TITLE_MAX,
            "max_card_subtitle_length": CARD_SUBTITLE_MAX,
            "max_card_text_length": CARD_TEXT_MAX,
            "max_card_buttons": CARD_BUTTONS_MAX,
            "max_button_title_length": BUTTON_TITLE_MAX,
            "supported_card_header_kinds": ["image", "video"],
        },
        "general": {
            "length_unit": "characters",
            "supported_platforms": ["whatsapp", "instagram"],
            "requires_authentication": True,
        },
    }
