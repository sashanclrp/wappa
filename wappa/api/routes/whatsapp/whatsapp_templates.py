"""Optional standalone Wappa HTTP adapter for Template transport."""

from fastapi import APIRouter, Depends, Request

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.messaging import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
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
    context: InboxExecutionContext,
) -> TemplateTransportResult:
    # The context already resolved this Inbox; reuse it rather than asking the
    # Inbox Directory a second time for the same request.
    transport = context.template_transport(http_request.app)
    return await transport.send(request)


@router.post("/send-text", response_model=TemplateTransportResult)
async def send_text_template(
    request: TextTemplateTransportRequest,
    http_request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> TemplateTransportResult:
    """Send a text Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request, context)


@router.post("/send-media", response_model=TemplateTransportResult)
async def send_media_template(
    request: MediaTemplateTransportRequest,
    http_request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> TemplateTransportResult:
    """Send a media-header Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request, context)


@router.post("/send-location", response_model=TemplateTransportResult)
async def send_location_template(
    request: LocationTemplateTransportRequest,
    http_request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> TemplateTransportResult:
    """Send a location-header Template through Wappa's Inbox-scoped transport."""
    return await _send(request, http_request, context)
