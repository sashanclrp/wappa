"""WhatsApp template management read endpoints."""

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query

from wappa.api.dependencies.whatsapp_dependencies import (
    get_whatsapp_template_info_service,
)
from wappa.messaging.whatsapp.models.template_info_models import (
    TemplateByIdRequest,
    TemplateByNameRequest,
    TemplateInfo,
    TemplateInfoListResponse,
    TemplateListRequest,
    TemplateNamespaceResponse,
)
from wappa.messaging.whatsapp.models.template_models import TemplateMessageStatus
from wappa.messaging.whatsapp.services import WhatsAppTemplateInfoService

router = APIRouter(
    prefix="/whatsapp/templates",
    tags=["WhatsApp - Templates Info"],
    responses={
        400: {"description": "Bad Request - Invalid template query parameters"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        403: {"description": "Forbidden - Template access denied"},
        404: {"description": "Not Found - Template or WABA resource not found"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)


def _raise_info_http_error(exc: aiohttp.ClientResponseError) -> None:
    """Translate Meta Graph API errors into FastAPI HTTP responses."""
    raise HTTPException(
        status_code=exc.status,
        detail=f"WhatsApp template info request failed: {exc.message or str(exc)}",
    ) from exc


@router.get(
    "/limits",
    summary="Get Template Message Limits",
    description="Get platform-level template message constraints exposed by Wappa",
)
async def get_template_limits() -> dict:
    """Return static template capability limits documented by Wappa."""
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
    "/info/by-id/{template_id}",
    response_model=TemplateInfo,
    summary="Get Template By ID",
    description="Fetch a WhatsApp template directly by template ID from Graph API",
)
async def get_template_by_id(
    template_id: str,
    fields: str | None = Query(
        default=None,
        description="Optional Graph API fields projection",
    ),
    service: WhatsAppTemplateInfoService = Depends(get_whatsapp_template_info_service),
) -> TemplateInfo:
    """Fetch template metadata using the template ID endpoint."""
    request_model = TemplateByIdRequest(template_id=template_id, fields=fields)
    try:
        return await service.get_template_by_id(request_model)
    except aiohttp.ClientResponseError as exc:
        _raise_info_http_error(exc)


@router.get(
    "/info/by-name/{template_name}",
    response_model=TemplateInfoListResponse,
    summary="Get Template By Name",
    description="Fetch WhatsApp templates by name from the WABA template collection",
)
async def get_template_by_name(
    template_name: str,
    fields: str | None = Query(
        default=None,
        description="Optional Graph API fields projection",
    ),
    service: WhatsAppTemplateInfoService = Depends(get_whatsapp_template_info_service),
) -> TemplateInfoListResponse:
    """Fetch template metadata using the WABA template collection filtered by name."""
    request_model = TemplateByNameRequest(
        template_name=template_name,
        fields=fields,
    )
    try:
        return await service.get_template_by_name(request_model)
    except aiohttp.ClientResponseError as exc:
        _raise_info_http_error(exc)


@router.get(
    "/info",
    response_model=TemplateInfoListResponse,
    summary="List Templates",
    description="List WhatsApp templates for the configured WABA",
)
async def list_templates(
    name: str | None = Query(
        default=None,
        description="Optional template name filter",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=100,
        description="Optional page size",
    ),
    after: str | None = Query(
        default=None,
        description="Optional pagination cursor for the next page",
    ),
    before: str | None = Query(
        default=None,
        description="Optional pagination cursor for the previous page",
    ),
    fields: str | None = Query(
        default=None,
        description="Optional Graph API fields projection",
    ),
    service: WhatsAppTemplateInfoService = Depends(get_whatsapp_template_info_service),
) -> TemplateInfoListResponse:
    """List templates from the configured WABA."""
    request_model = TemplateListRequest(
        name=name,
        limit=limit,
        after=after,
        before=before,
        fields=fields,
    )
    try:
        return await service.list_templates(request_model)
    except aiohttp.ClientResponseError as exc:
        _raise_info_http_error(exc)


@router.get(
    "/info/namespace",
    response_model=TemplateNamespaceResponse,
    summary="Get Template Namespace",
    description="Fetch the message template namespace for the configured WABA",
)
async def get_template_namespace(
    service: WhatsAppTemplateInfoService = Depends(get_whatsapp_template_info_service),
) -> TemplateNamespaceResponse:
    """Fetch WABA namespace metadata used for template management."""
    try:
        return await service.get_template_namespace()
    except aiohttp.ClientResponseError as exc:
        _raise_info_http_error(exc)


@router.get(
    "/status/{template_name}",
    response_model=TemplateMessageStatus,
    summary="Get Template Status",
    description="Resolve a template by name and return a compatibility status payload",
)
async def get_template_status(
    template_name: str,
    service: WhatsAppTemplateInfoService = Depends(get_whatsapp_template_info_service),
) -> TemplateMessageStatus:
    """Compatibility endpoint backed by the real template info service."""
    try:
        response = await service.get_template_by_name(
            TemplateByNameRequest(template_name=template_name)
        )
    except aiohttp.ClientResponseError as exc:
        _raise_info_http_error(exc)

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_name}' was not found",
        )

    template = response.data[0]
    return TemplateMessageStatus(
        template_name=template.name,
        status=template.status or "UNKNOWN",
        language=template.language or "unknown",
        category=template.category,
        components=[
            component.model_dump()
            if hasattr(component, "model_dump")
            else component
            for component in template.components
        ],
    )
