"""WhatsApp Inbox health under ``GET /api/whatsapp/health``.

Resolves the selected Inbox and reports which Inbox and Graph API version the
routes behind it use. It makes no Meta call.
"""

from fastapi import APIRouter, Depends

from wappa.api.dependencies.inbox_context import (
    InboxExecutionContext,
    get_inbox_execution_context,
)
from wappa.core.config.settings import settings

router = APIRouter(tags=["WhatsApp - Health"])


@router.get(
    "/health",
    summary="WhatsApp Inbox Health",
    description=(
        "Resolve the selected WhatsApp Inbox and report its Platform, Inbox ID "
        "and Graph API version."
    ),
)
async def whatsapp_health_check(
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> dict:
    return {
        "status": "healthy",
        "platform": context.inbox_ref.platform.value,
        "inbox_id": context.inbox_id,
        "api_version": context.graph_api_version or settings.api_version,
    }
