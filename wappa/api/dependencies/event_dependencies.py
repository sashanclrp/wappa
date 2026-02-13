"""
Event dispatcher dependency injection for API routes.

Provides access to the APIEventDispatcher for dispatching
outgoing message events from API routes.

Important: Pass the FastAPI Request object to dispatch functions to enable
database session injection in process_api_message() handlers.
"""

import asyncio
from typing import TYPE_CHECKING

from fastapi import Request

from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.core.logging.context import (
    get_current_owner_context,
    get_current_tenant_context,
)
from wappa.domain.events.api_message_event import APIMessageEvent

if TYPE_CHECKING:
    from wappa.messaging.whatsapp.models.basic_models import MessageResult


def get_api_event_dispatcher(request: Request) -> APIEventDispatcher | None:
    """
    Get API event dispatcher from app state.

    The dispatcher is created during app startup with the registered event handler.
    Returns None if no handler is registered (allows routes to skip event dispatch).

    Args:
        request: FastAPI request object

    Returns:
        APIEventDispatcher if registered, None otherwise
    """
    return getattr(request.app.state, "api_event_dispatcher", None)


async def dispatch_api_message_event(
    dispatcher: APIEventDispatcher | None,
    message_type: str,
    result: "MessageResult",
    request_payload: dict,
    recipient: str,
    request: Request | None = None,
) -> None:
    """
    Fire-and-forget API event dispatch helper with database session support.

    Creates an APIMessageEvent from the message result and dispatches it
    asynchronously without blocking the API response.

    Important: Pass the FastAPI `request` parameter to enable database session
    injection in process_api_message() handlers. Without it, self.db will be None.

    Args:
        dispatcher: APIEventDispatcher or None (skips if None)
        message_type: Type of message (text, image, template, etc.)
        result: MessageResult from the messenger
        request_payload: Original API request payload
        recipient: Recipient phone number
        request: FastAPI Request for database session access (recommended)
    """
    if dispatcher is None:
        return

    event = APIMessageEvent(
        message_type=message_type,
        message_id=result.message_id,
        recipient=recipient,
        request_payload=request_payload,
        response_success=result.success,
        response_error=result.error,
        meta_response=getattr(result, "raw_response", None),
        tenant_id=get_current_tenant_context() or "unknown",
        owner_id=get_current_owner_context(),
    )

    # Fire and forget - don't block the API response
    # Pass request to enable DB session injection in handler
    asyncio.create_task(dispatcher.dispatch(event, request))
