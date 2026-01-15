"""
WhatsApp interactive messaging API endpoints.

Provides REST API endpoints for WhatsApp interactive operations:
- POST /api/whatsapp/interactive/send-buttons: Send button messages
- POST /api/whatsapp/interactive/send-list: Send list messages
- POST /api/whatsapp/interactive/send-cta: Send call-to-action messages

Router configuration:
- Prefix: /whatsapp/interactive
- Tags: ["WhatsApp - Interactive"]
- Full URL: /api/whatsapp/interactive/ (when included with /api prefix)
"""

from fastapi import APIRouter, Depends, HTTPException

from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_messenger
from wappa.api.utils import (
    convert_list_sections_to_dict,
    dispatch_message_event,
    raise_for_failed_result,
)
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.interactive_models import (
    ButtonMessage,
    CTAMessage,
    ListMessage,
)

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

# Create router with WhatsApp Interactive configuration
router = APIRouter(
    prefix="/whatsapp/interactive",
    tags=["WhatsApp - Interactive"],
    responses={
        400: {"description": "Bad Request - Invalid interactive message format"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        404: {"description": "Not Found - Recipient or resource not found"},
        413: {"description": "Payload Too Large - Interactive content too large"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/send-buttons",
    response_model=MessageResult,
    summary="Send Button Message",
    description="Send an interactive button message with up to 3 quick reply buttons",
)
@dispatch_message_event("button")
async def send_button_message(
    request: ButtonMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive button message via WhatsApp.

    Supports up to 3 quick reply buttons with optional header and footer.
    Based on WhatsApp Cloud API 2025 interactive button specifications.
    """
    try:
        result = await messenger.send_button_message(
            buttons=request.buttons,
            recipient=request.recipient,
            body=request.body,
            header=request.header,
            footer=request.footer,
            reply_to_message_id=request.reply_to_message_id,
        )

        raise_for_failed_result(result, "send button message", INTERACTIVE_ERROR_GROUPS)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send button message: {str(e)}"
        ) from e


@router.post(
    "/send-list",
    response_model=MessageResult,
    summary="Send List Message",
    description="Send an interactive list message with sectioned rows",
)
@dispatch_message_event("list")
async def send_list_message(
    request: ListMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send interactive list message via WhatsApp.

    Supports sectioned lists with up to 10 sections and 10 rows per section.
    Based on WhatsApp Cloud API 2025 interactive list specifications.
    """
    try:
        result = await messenger.send_list_message(
            sections=convert_list_sections_to_dict(request.sections),
            recipient=request.recipient,
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
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send list message: {str(e)}"
        ) from e


@router.post(
    "/send-cta",
    response_model=MessageResult,
    summary="Send Call-to-Action Message",
    description="Send an interactive call-to-action message with URL button",
)
@dispatch_message_event("cta")
async def send_cta_message(
    request: CTAMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
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
            recipient=request.recipient,
            body=request.body,
            header=request.header,
            footer=request.footer,
            reply_to_message_id=request.reply_to_message_id,
        )

        raise_for_failed_result(result, "send CTA message", INTERACTIVE_ERROR_GROUPS)
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send CTA message: {str(e)}"
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


# Example endpoint demonstrating complex interactive message construction
@router.post(
    "/send-complex-buttons",
    response_model=MessageResult,
    summary="Send Complex Button Message (Example)",
    description="Example endpoint showing complex button message with all features",
)
async def send_complex_button_message(
    recipient: str, messenger: IMessenger = Depends(get_whatsapp_messenger)
) -> MessageResult:
    """Example endpoint demonstrating complex button message construction.

    This endpoint shows how to create a button message with header, footer,
    and multiple buttons programmatically.
    """
    try:
        buttons = [
            {"id": "yes_button", "title": "Yes"},
            {"id": "no_button", "title": "No"},
            {"id": "maybe_button", "title": "Maybe"},
        ]
        header = {"type": "text", "text": "Quick Decision Required"}

        result = await messenger.send_button_message(
            buttons=buttons,
            recipient=recipient,
            body="Would you like to proceed with this action? Please choose one of the options below.",
            header=header,
            footer="This message will expire in 24 hours",
        )

        raise_for_failed_result(
            result, "send complex button message", INTERACTIVE_ERROR_GROUPS
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send complex button message: {str(e)}"
        ) from e


# Example endpoint for list messages
@router.post(
    "/send-menu-list",
    response_model=MessageResult,
    summary="Send Menu List Message (Example)",
    description="Example endpoint showing menu-style list message",
)
async def send_menu_list_message(
    recipient: str, messenger: IMessenger = Depends(get_whatsapp_messenger)
) -> MessageResult:
    """Example endpoint demonstrating menu-style list message construction.

    This endpoint shows how to create a restaurant menu using list messages.
    """
    try:
        sections = [
            {
                "title": "Main Dishes",
                "rows": [
                    {
                        "id": "pizza_margherita",
                        "title": "Pizza Margherita",
                        "description": "Classic tomato and mozzarella - $12.99",
                    },
                    {
                        "id": "pasta_carbonara",
                        "title": "Pasta Carbonara",
                        "description": "Creamy bacon pasta - $14.99",
                    },
                ],
            },
            {
                "title": "Salads",
                "rows": [
                    {
                        "id": "caesar_salad",
                        "title": "Caesar Salad",
                        "description": "Crispy romaine with parmesan - $8.99",
                    },
                    {
                        "id": "greek_salad",
                        "title": "Greek Salad",
                        "description": "Fresh vegetables with feta - $9.99",
                    },
                ],
            },
            {
                "title": "Beverages",
                "rows": [
                    {
                        "id": "coke",
                        "title": "Coca Cola",
                        "description": "Classic refreshing cola - $2.99",
                    },
                    {
                        "id": "water",
                        "title": "Sparkling Water",
                        "description": "Refreshing mineral water - $1.99",
                    },
                ],
            },
        ]

        result = await messenger.send_list_message(
            sections=sections,
            recipient=recipient,
            body="Welcome to our restaurant! Browse our menu and select what you'd like to order.",
            button_text="View Menu",
            header="Restaurant Menu",
            footer="Prices include tax - Free delivery over $25",
        )

        raise_for_failed_result(
            result, "send menu list message", INTERACTIVE_ERROR_GROUPS
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send menu list message: {str(e)}"
        ) from e
