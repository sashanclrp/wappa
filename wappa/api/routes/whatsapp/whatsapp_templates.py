"""
WhatsApp template messaging API endpoints.

Provides REST API endpoints for WhatsApp Business template operations:
- POST /api/whatsapp/templates/send-text: Send text-only templates
- POST /api/whatsapp/templates/send-media: Send templates with media headers
- POST /api/whatsapp/templates/send-location: Send templates with location headers
- GET /api/whatsapp/templates/health: Service health check

Router configuration:
- Prefix: /whatsapp/templates
- Tags: ["WhatsApp - Templates"]
- Full URL: /api/whatsapp/templates/ (when included with /api prefix)

State Management:
All send endpoints support optional state_config for creating user cache state
when the template is sent successfully. This enables routing subsequent user
responses to specific handlers based on the template context.

AI Agent Context (template_metadata):
All send endpoints support optional template_metadata for providing AI agent
context. This metadata is NOT sent to WhatsApp - it's for internal use only
to provide additional context, instructions, and constraints for AI processing.
The system_message field can be used to attach system-level instructions for
AI agents to process within their context.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from wappa.api.dependencies.cache_dependencies import get_template_state_service
from wappa.api.dependencies.event_dependencies import get_api_event_dispatcher
from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_messenger
from wappa.api.services.template_state_service import TemplateStateService
from wappa.api.utils import (
    convert_body_parameters,
    dispatch_message_event,
    raise_for_failed_result,
)
from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.template_models import (
    LocationTemplateMessage,
    MediaTemplateMessage,
    TemplateMessageStatus,
    TextTemplateMessage,
)

# Error code to HTTP status mapping for template operations
TEMPLATE_ERROR_GROUPS = {
    ("TEMPLATE_NOT_FOUND", "TEMPLATE_NOT_APPROVED"): 403,
    (
        "INVALID_PARAMETERS",
        "MISSING_PARAMETERS",
        "INVALID_MEDIA_TYPE",
        "MEDIA_NOT_FOUND",
        "INVALID_COORDINATES",
    ): 400,
    (
        "TEMPLATE_SEND_FAILED",
        "MEDIA_TEMPLATE_SEND_FAILED",
        "LOCATION_TEMPLATE_SEND_FAILED",
    ): 500,
}


async def _maybe_set_template_state(
    result: MessageResult,
    request: TextTemplateMessage | MediaTemplateMessage | LocationTemplateMessage,
    state_service: TemplateStateService,
) -> None:
    """Set template state if configured and send was successful."""
    if request.state_config and result.success:
        await state_service.set_template_state(
            recipient=request.recipient,
            state_config=request.state_config,
            message_id=result.message_id,
            template_name=request.template_name,
        )


# Create router with WhatsApp Templates configuration
router = APIRouter(
    prefix="/whatsapp/templates",
    tags=["WhatsApp - Templates"],
    responses={
        400: {"description": "Bad Request - Invalid template format or parameters"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        403: {"description": "Forbidden - Template not approved or access denied"},
        404: {"description": "Not Found - Template not found"},
        413: {"description": "Payload Too Large - Template content too large"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/send-text",
    response_model=MessageResult,
    summary="Send Text Template Message",
    description="Send a text-only template message with optional state configuration",
)
@dispatch_message_event("text_template")
async def send_text_template(
    request: TextTemplateMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    state_service: TemplateStateService = Depends(get_template_state_service),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send text-only template message via WhatsApp.

    Sends pre-approved business templates with dynamic parameter substitution.
    Templates must be approved by WhatsApp before use.

    If state_config is provided, creates a user cache state for routing
    subsequent responses based on template-{state_value}.

    If template_metadata is provided, includes AI context (text_content, system_message)
    for internal AI agent processing. This metadata is NOT sent to WhatsApp.
    """
    result = await messenger.send_text_template(
        template_name=request.template_name,
        recipient=request.recipient,
        body_parameters=convert_body_parameters(request.body_parameters),
        language_code=request.language.code,
    )

    raise_for_failed_result(result, "send text template", TEMPLATE_ERROR_GROUPS)
    await _maybe_set_template_state(result, request, state_service)
    return result


@router.post(
    "/send-media",
    response_model=MessageResult,
    summary="Send Media Template Message",
    description="Send a template message with media header and optional state configuration",
)
@dispatch_message_event("media_template")
async def send_media_template(
    request: MediaTemplateMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    state_service: TemplateStateService = Depends(get_template_state_service),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send template message with media header via WhatsApp.

    Supports templates with image, video, or document headers.
    Either media_id (uploaded media) or media_url (external media) must be provided.

    If state_config is provided, creates a user cache state for routing
    subsequent responses based on template-{state_value}.

    If template_metadata is provided, includes AI context (text_content, media_description,
    media_transcript, system_message) for internal AI agent processing.
    This metadata is NOT sent to WhatsApp.
    """
    result = await messenger.send_media_template(
        template_name=request.template_name,
        recipient=request.recipient,
        media_type=request.media_type.value,
        media_id=request.media_id,
        media_url=request.media_url,
        body_parameters=convert_body_parameters(request.body_parameters),
        language_code=request.language.code,
    )

    raise_for_failed_result(result, "send media template", TEMPLATE_ERROR_GROUPS)
    await _maybe_set_template_state(result, request, state_service)
    return result


@router.post(
    "/send-location",
    response_model=MessageResult,
    summary="Send Location Template Message",
    description="Send a template message with location header and optional state configuration",
)
@dispatch_message_event("location_template")
async def send_location_template(
    request: LocationTemplateMessage,
    fastapi_request: Request,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
    state_service: TemplateStateService = Depends(get_template_state_service),
    api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
) -> MessageResult:
    """Send template message with location header via WhatsApp.

    Supports templates with geographic location headers showing a map preview.
    Coordinates must be valid latitude (-90 to 90) and longitude (-180 to 180).

    If state_config is provided, creates a user cache state for routing
    subsequent responses based on template-{state_value}.

    If template_metadata is provided, includes AI context (text_content, system_message)
    for internal AI agent processing. This metadata is NOT sent to WhatsApp.
    """
    result = await messenger.send_location_template(
        template_name=request.template_name,
        recipient=request.recipient,
        latitude=request.latitude,
        longitude=request.longitude,
        name=request.name,
        address=request.address,
        body_parameters=convert_body_parameters(request.body_parameters),
        language_code=request.language.code,
    )

    raise_for_failed_result(result, "send location template", TEMPLATE_ERROR_GROUPS)
    await _maybe_set_template_state(result, request, state_service)
    return result


@router.get(
    "/limits",
    summary="Get Template Message Limits",
    description="Get platform-specific template message limits and constraints",
)
async def get_template_limits() -> dict:
    """Get WhatsApp template message limits and constraints.

    Returns supported template types, parameter limits, and platform constraints.
    """
    return {
        "text_templates": {
            "max_body_parameters": 10,
            "max_parameter_length": 1024,
            "supported_parameter_types": ["text", "currency", "date_time"],
            "supported_languages": [
                "es",
                "en",
                "en_US",
                "pt_BR",
                "fr",
                "de",
                "it",
                "ja",
                "ko",
                "zh",
            ],
        },
        "media_templates": {
            "supported_media_types": ["image", "video", "document"],
            "max_body_parameters": 10,
            "media_requirements": {
                "image": {"formats": ["JPEG", "PNG"], "max_size": "5MB"},
                "video": {"formats": ["MP4", "3GP"], "max_size": "16MB"},
                "document": {
                    "formats": ["PDF", "DOC", "DOCX", "XLS", "XLSX"],
                    "max_size": "100MB",
                },
            },
        },
        "location_templates": {
            "coordinate_ranges": {
                "latitude": {"min": -90, "max": 90},
                "longitude": {"min": -180, "max": 180},
            },
            "max_name_length": 100,
            "max_address_length": 1000,
            "max_body_parameters": 10,
        },
        "general": {
            "requires_approval": True,
            "approval_process": "WhatsApp Business Account Manager",
            "rate_limits": "Per WhatsApp Business API terms",
            "supported_platforms": ["whatsapp"],
            "requires_authentication": True,
        },
    }


@router.get(
    "/status/{template_name}",
    response_model=TemplateMessageStatus,
    summary="Get Template Status",
    description="Get the approval status and configuration of a specific template",
)
async def get_template_status(
    template_name: str,
    language: str = "es",
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> TemplateMessageStatus:
    """Get template status and configuration.

    Returns the approval status, category, and components of a WhatsApp template.
    """
    try:
        # This would typically call the template handler's get_template_info method
        # For now, return a mock status structure
        return TemplateMessageStatus(
            template_name=template_name,
            status="APPROVED",  # This should come from actual API
            language=language,
            category="MARKETING",  # This should come from actual API
            components=[
                {"type": "HEADER", "format": "TEXT"},
                {"type": "BODY", "text": "Template body with parameters"},
                {"type": "FOOTER", "text": "Optional footer text"},
            ],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get template status: {str(e)}"
        ) from e


# Example endpoint demonstrating complex template usage
@router.post(
    "/send-welcome-template",
    response_model=MessageResult,
    summary="Send Welcome Template (Example)",
    description="Example endpoint showing complex template message with parameters",
)
async def send_welcome_template(
    recipient: str,
    customer_name: str,
    business_name: str = "Mimeia Hotel",
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> MessageResult:
    """Example endpoint demonstrating welcome template with parameters.

    This endpoint shows how to create a complex template message with
    multiple parameters and proper error handling.
    """
    try:
        # Example welcome template parameters
        body_parameters = [
            {"type": "text", "text": customer_name},
            {"type": "text", "text": business_name},
        ]

        result = await messenger.send_text_template(
            template_name="welcome_customer",
            recipient=recipient,
            body_parameters=body_parameters,
            language_code="es",
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send welcome template: {str(e)}"
        ) from e


# Example endpoint for media template with location
@router.post(
    "/send-store-location-template",
    response_model=MessageResult,
    summary="Send Store Location Template (Example)",
    description="Example endpoint showing location template for business use",
)
async def send_store_location_template(
    recipient: str,
    store_name: str = "Main Store",
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> MessageResult:
    """Example endpoint demonstrating store location template.

    This endpoint shows how to create a location-based template for
    business location sharing with customers.
    """
    try:
        # Example store location (replace with actual coordinates)
        result = await messenger.send_location_template(
            template_name="store_location",
            recipient=recipient,
            latitude="37.483307",
            longitude="-122.148981",
            name=store_name,
            address="123 Business Ave, Business City, BC 12345",
            body_parameters=[
                {"type": "text", "text": store_name},
                {"type": "text", "text": "Mon-Fri 9AM-6PM"},
            ],
            language_code="es",
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send store location template: {str(e)}"
        ) from e
