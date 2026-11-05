"""
WhatsApp interactive messaging API endpoints.

Provides REST API endpoints for WhatsApp interactive operations:
- POST /api/whatsapp/interactive/send-buttons: Send button messages
- POST /api/whatsapp/interactive/send-list: Send list messages
- POST /api/whatsapp/interactive/send-cta: Send call-to-action messages
- POST /api/{platform}/interactive/send-carousel: Send a card carousel

Router configuration:
- Prefix: /interactive
- Tags: ["WhatsApp - Interactive"]
- Full URL: /api/whatsapp/interactive/
"""

from fastapi import Depends, HTTPException, Request
from pydantic import Field

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.inbox_context import get_inbox_messenger
from wappa.api.routes.whatsapp.route_families import RouteFamily
from wappa.api.utils import (
    dispatch_message_event,
    raise_for_failed_result,
)
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interactive import MessageCard
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.messaging_targets import (
    DeliveryAddresses,
    DirectMessage,
    UnsupportedOperationError,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    ButtonMessage,
    CTAMessage,
    ListMessage,
)
from wappa.schemas.core.recipient import DeliveryRequest

# Error code groups for interactive operations
_SIZE_ERRORS = (
    "BODY_TOO_LONG",
    "FOOTER_TOO_LONG",
    "BUTTON_TITLE_TOO_LONG",
    "BUTTON_ID_TOO_LONG",
    "BUTTON_TEXT_TOO_LONG",
    "HEADER_TOO_LONG",
)
_VALIDATION_ERRORS = (
    "INVALID_HEADER_TYPE",
    "INVALID_TEXT_HEADER",
    "INVALID_MEDIA_HEADER",
    "TOO_MANY_SECTIONS",
    "TOO_MANY_ROWS",
    "SECTION_TITLE_TOO_LONG",
    "ROW_TITLE_TOO_LONG",
    "ROW_ID_TOO_LONG",
    "ROW_DESCRIPTION_TOO_LONG",
    "DUPLICATE_ROW_ID",
    "MISSING_REQUIRED_PARAMS",
    "INVALID_URL_FORMAT",
)

# Error code to HTTP status mapping
INTERACTIVE_ERROR_GROUPS = {
    _SIZE_ERRORS: 413,
    _VALIDATION_ERRORS: 400,
}

# Interactive sends are omissible outbound mutations; the limits endpoint
# is a read an embedding host still uses for admission checks.
_family = RouteFamily(
    prefix="/interactive",
    tags=["WhatsApp - Interactive"],
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
@dispatch_message_event(platform="whatsapp")
async def send_button_message(
    request: ButtonMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive button message via WhatsApp.

    Supports up to 3 quick reply buttons with optional header and footer.
    Based on WhatsApp Cloud API 2025 interactive button specifications.
    """
    try:
        result = await messenger.send_button_message(
            buttons=request.buttons,
            target=DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient, *request.addresses),
            ),
            body=request.body,
            header=request.header,
            footer=request.footer,
            reply_to_message_id=request.reply_to_message_id,
        )

        raise_for_failed_result(result, "send button message", INTERACTIVE_ERROR_GROUPS)
        return result

    except HTTPException:
        raise
    except UnsupportedOperationError as e:  # not on this Platform
        raise HTTPException(status_code=501, detail=str(e)) from e
    except ValueError as e:  # rejected locally, before any Platform call
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send button message to '{request.recipient}': {type(e).__name__}: {e}",
        ) from e


@send_router.post(
    "/send-list",
    response_model=MessageResult,
    summary="Send List Message",
    description="Send an interactive list message with sectioned rows",
)
@dispatch_message_event(platform="whatsapp")
async def send_list_message(
    request: ListMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive list message via WhatsApp.

    Supports sectioned lists with up to 10 sections and 10 rows per section.
    Based on WhatsApp Cloud API 2025 interactive list specifications.
    """
    try:
        result = await messenger.send_list_message(
            sections=request.sections,
            target=DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient, *request.addresses),
            ),
            body=request.body,
            button_text=request.button_text,
            header=request.header,
            footer=request.footer,
            reply_to_message_id=request.reply_to_message_id,
        )

        raise_for_failed_result(result, "send list message", INTERACTIVE_ERROR_GROUPS)
        return result

    except HTTPException:
        raise
    except UnsupportedOperationError as e:  # not on this Platform
        raise HTTPException(status_code=501, detail=str(e)) from e
    except ValueError as e:  # rejected locally, before any Platform call
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send list message to '{request.recipient}': {type(e).__name__}: {e}",
        ) from e


@send_router.post(
    "/send-cta",
    response_model=MessageResult,
    summary="Send Call-to-Action Message",
    description="Send an interactive call-to-action message with URL button",
)
@dispatch_message_event(platform="whatsapp")
async def send_cta_message(
    request: CTAMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive call-to-action message via WhatsApp.

    Supports external URL buttons for call-to-action scenarios.
    Based on WhatsApp Cloud API 2025 CTA URL specifications.
    """
    try:
        result = await messenger.send_cta_message(
            button_text=request.button_text,
            button_url=request.button_url,
            target=DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient, *request.addresses),
            ),
            body=request.body,
            header=request.header,
            footer=request.footer,
            reply_to_message_id=request.reply_to_message_id,
        )

        raise_for_failed_result(result, "send CTA message", INTERACTIVE_ERROR_GROUPS)
        return result

    except HTTPException:
        raise
    except UnsupportedOperationError as e:  # not on this Platform
        raise HTTPException(status_code=501, detail=str(e)) from e
    except ValueError as e:  # rejected locally, before any Platform call
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send CTA message to '{request.recipient}': {type(e).__name__}: {e}",
        ) from e


class CarouselMessage(DeliveryRequest):
    """A carousel of 2–10 cards (``IMessenger.send_carousel``)."""

    body: str = Field(..., min_length=1, description="Text shown with the carousel")
    cards: list[MessageCard] = Field(..., min_length=1, max_length=10)


@send_router.post(
    "/send-carousel",
    response_model=MessageResult,
    summary="Send Carousel",
    description=(
        "Send a card carousel. WhatsApp: media carousel, 2–10 cards, each with "
        "`image_url` and the same button kind and count. Instagram: generic "
        "template carousel. Platform rules are checked before any call (400)."
    ),
)
@dispatch_message_event("carousel")
async def send_carousel_message(
    request: CarouselMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_inbox_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    try:
        result = await messenger.send_carousel(
            request.cards,
            DirectMessage(
                inbox_ref=InboxRef(
                    platform=messenger.platform, inbox_id=messenger.inbox_id
                ),
                addresses=DeliveryAddresses.of(request.recipient, *request.addresses),
            ),
            request.body,
        )
        raise_for_failed_result(result, "send carousel", INTERACTIVE_ERROR_GROUPS)
        return result
    except HTTPException:
        raise
    except UnsupportedOperationError as e:  # not on this Platform
        raise HTTPException(status_code=501, detail=str(e)) from e
    except ValueError as e:  # rejected locally, before any Platform call
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send carousel to '{request.recipient}': {type(e).__name__}: {e}",
        ) from e


@router.get(
    "/limits",
    summary="Get Interactive Message Limits",
    description="Get platform-specific interactive message limits and constraints",
)
async def get_interactive_limits() -> dict:
    """Get WhatsApp interactive message limits and constraints.

    Returns supported interactive types, size limits, and platform constraints.
    """
    return {
        "button_messages": {
            "max_buttons": 3,
            "max_button_title_length": 20,
            "max_button_id_length": 256,
            "max_body_length": 1024,
            "max_footer_length": 60,
            "supported_header_types": ["text", "image", "video", "document"],
        },
        "list_messages": {
            "max_sections": 10,
            "max_rows_per_section": 10,
            "max_button_text_length": 20,
            "max_body_length": 4096,
            "max_header_length": 60,
            "max_footer_length": 60,
            "max_section_title_length": 24,
            "max_row_title_length": 24,
            "max_row_description_length": 72,
            "max_row_id_length": 200,
        },
        "cta_messages": {
            "required_url_protocols": ["http://", "https://"],
            "max_body_length": 4096,
            "max_button_text_length": 256,
            "max_header_length": 60,
            "max_footer_length": 60,
        },
        "general": {
            "supported_platforms": ["whatsapp"],
            "requires_authentication": True,
            "rate_limits": "Per WhatsApp Business API terms",
        },
    }
