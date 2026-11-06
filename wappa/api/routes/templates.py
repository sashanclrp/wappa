"""Template transport routes under ``/api/{platform}/templates``.

Mounted only with ``include_template_transport``. The router gates on the
Inbox's ``ITemplateMessaging`` capability, so a Platform without Templates
answers 501 and a Platform that gains them serves these routes unchanged.
"""

from fastapi import APIRouter, Depends, Request

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
    requires_capability,
)
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.messaging import (
    LocationTemplateTransportRequest,
    MediaTemplateTransportRequest,
    TemplateTransportResult,
    TextTemplateTransportRequest,
)

router = APIRouter(
    prefix="/templates",
    tags=["Template Transport"],
    dependencies=[Depends(requires_capability(ITemplateMessaging))],
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
