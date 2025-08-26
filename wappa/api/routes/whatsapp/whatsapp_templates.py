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
"""

from fastapi import APIRouter, Depends, HTTPException

from wappa.api.dependencies.whatsapp_dependencies import get_whatsapp_messenger
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.messaging.whatsapp.models.template_models import (
    LocationTemplateMessage,
    MediaTemplateMessage,
    TemplateMessageStatus,
    TextTemplateMessage,
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
    description="Send a text-only template message with parameter substitution",
)
async def send_text_template(
    request: TextTemplateMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> MessageResult:
    """Send text-only template message via WhatsApp.

    Sends pre-approved business templates with dynamic parameter substitution.
    Templates must be approved by WhatsApp before use.
    """
    try:
        # Convert Pydantic model to dict format expected by messenger
        body_parameters = None
        if request.body_parameters:
            body_parameters = []
            for param in request.body_parameters:
                body_parameters.append({"type": param.type.value, "text": param.text})

        result = await messenger.send_text_template(
            template_name=request.template_name,
            recipient=request.recipient,
            body_parameters=body_parameters,
            language_code=request.language.code,
        )

        if not result.success:
            # Map specific template error codes to HTTP status codes
            if result.error_code in ["TEMPLATE_NOT_FOUND", "TEMPLATE_NOT_APPROVED"]:
                raise HTTPException(status_code=403, detail=result.error)
            elif result.error_code in ["INVALID_PARAMETERS", "MISSING_PARAMETERS"]:
                raise HTTPException(status_code=400, detail=result.error)
            elif result.error_code in ["TEMPLATE_SEND_FAILED"]:
                raise HTTPException(status_code=500, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send text template: {str(e)}"
        )


@router.post(
    "/send-media",
    response_model=MessageResult,
    summary="Send Media Template Message",
    description="Send a template message with media header (image, video, or document)",
)
async def send_media_template(
    request: MediaTemplateMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> MessageResult:
    """Send template message with media header via WhatsApp.

    Supports templates with image, video, or document headers.
    Either media_id (uploaded media) or media_url (external media) must be provided.
    """
    try:
        # Convert Pydantic model to dict format expected by messenger
        body_parameters = None
        if request.body_parameters:
            body_parameters = []
            for param in request.body_parameters:
                body_parameters.append({"type": param.type.value, "text": param.text})

        result = await messenger.send_media_template(
            template_name=request.template_name,
            recipient=request.recipient,
            media_type=request.media_type.value,
            media_id=request.media_id,
            media_url=request.media_url,
            body_parameters=body_parameters,
            language_code=request.language.code,
        )

        if not result.success:
            # Map specific template error codes to HTTP status codes
            if result.error_code in ["TEMPLATE_NOT_FOUND", "TEMPLATE_NOT_APPROVED"]:
                raise HTTPException(status_code=403, detail=result.error)
            elif result.error_code in [
                "INVALID_MEDIA_TYPE",
                "MEDIA_NOT_FOUND",
                "INVALID_PARAMETERS",
            ]:
                raise HTTPException(status_code=400, detail=result.error)
            elif result.error_code in ["MEDIA_TEMPLATE_SEND_FAILED"]:
                raise HTTPException(status_code=500, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send media template: {str(e)}"
        )


@router.post(
    "/send-location",
    response_model=MessageResult,
    summary="Send Location Template Message",
    description="Send a template message with location header and map preview",
)
async def send_location_template(
    request: LocationTemplateMessage,
    messenger: IMessenger = Depends(get_whatsapp_messenger),
) -> MessageResult:
    """Send template message with location header via WhatsApp.

    Supports templates with geographic location headers showing a map preview.
    Coordinates must be valid latitude (-90 to 90) and longitude (-180 to 180).
    """
    try:
        # Convert Pydantic model to dict format expected by messenger
        body_parameters = None
        if request.body_parameters:
            body_parameters = []
            for param in request.body_parameters:
                body_parameters.append({"type": param.type.value, "text": param.text})

        result = await messenger.send_location_template(
            template_name=request.template_name,
            recipient=request.recipient,
            latitude=request.latitude,
            longitude=request.longitude,
            name=request.name,
            address=request.address,
            body_parameters=body_parameters,
            language_code=request.language.code,
        )

        if not result.success:
            # Map specific template error codes to HTTP status codes
            if result.error_code in ["TEMPLATE_NOT_FOUND", "TEMPLATE_NOT_APPROVED"]:
                raise HTTPException(status_code=403, detail=result.error)
            elif result.error_code in ["INVALID_COORDINATES", "INVALID_PARAMETERS"]:
                raise HTTPException(status_code=400, detail=result.error)
            elif result.error_code in ["LOCATION_TEMPLATE_SEND_FAILED"]:
                raise HTTPException(status_code=500, detail=result.error)
            else:
                raise HTTPException(status_code=400, detail=result.error)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send location template: {str(e)}"
        )


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
        )


@router.get(
    "/health",
    summary="Template Service Health Check",
    description="Check health status of template messaging services",
)
async def health_check(messenger: IMessenger = Depends(get_whatsapp_messenger)) -> dict:
    """Health check for template messaging services.

    Returns service status and configuration information.
    """
    return {
        "status": "healthy",
        "service": "whatsapp-templates",
        "platform": messenger.platform.value,
        "tenant_id": messenger.tenant_id,
        "template_types": ["text", "media", "location"],
        "message_types_supported": [
            "text",
            "image",
            "video",
            "audio",
            "document",
            "sticker",
            "button",
            "list",
            "cta_url",
            "text_template",
            "media_template",
            "location_template",
        ],
        "features": [
            "Parameter substitution",
            "Multi-language support",
            "Media header templates",
            "Location header templates",
            "Template approval status",
        ],
    }


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
        )


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
        )
