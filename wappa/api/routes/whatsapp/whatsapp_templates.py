"""Optional standalone Wappa HTTP adapter for Template transport."""

from fastapi import APIRouter, Request

from wappa.api.utils.inbox_helpers import require_inbox_context
from wappa.messaging import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    OutboundRuntime,
    TemplateTransportResult,
    TextTemplateTransportRequest,
)

router = APIRouter(
    prefix="/templates",
    tags=["WhatsApp - Template Transport"],
)


async def _send(
    request: TextTemplateTransportRequest
    | MediaTemplateTransportRequest
    | LocationTemplateTransportRequest,
    http_request: Request,
) -> TemplateTransportResult:
    transport = OutboundRuntime.from_app(http_request.app).templates(
        require_inbox_context()
    )
    return await transport.send(request)


@router.post("/send-text", response_model=TemplateTransportResult)
async def send_text_template(
    request: TextTemplateTransportRequest,
    http_request: Request,
) -> TemplateTransportResult:
    """Send a text Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request)


@router.post("/send-media", response_model=TemplateTransportResult)
async def send_media_template(
    request: MediaTemplateTransportRequest,
    http_request: Request,
) -> TemplateTransportResult:
    """Send a media-header Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request)


@router.post("/send-location", response_model=TemplateTransportResult)
async def send_location_template(
    request: LocationTemplateTransportRequest,
    http_request: Request,
) -> TemplateTransportResult:
    """Send a location-header Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request)
