"""
API event dispatch decorators for route handlers.

Provides decorator-based event dispatch for WhatsApp API routes,
eliminating repetitive dispatch_api_message_event calls across route files.

The decorator automatically dispatches API events after successful route execution,
using fire-and-forget pattern (asyncio.create_task) to avoid blocking responses.

Database Session Support:
    When PostgresDatabasePlugin is configured, process_api_message() handlers
    have access to self.db for database operations. The decorator extracts
    the FastAPI Request from route parameters to enable this injection.
"""

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from wappa.core.events.api_event_dispatcher import APIEventDispatcher
from wappa.core.logging.context import (
    get_current_owner_context,
    get_current_tenant_context,
)
from wappa.domain.events.api_message_event import APIMessageEvent
from wappa.messaging.whatsapp.models.basic_models import MessageResult

if TYPE_CHECKING:
    from fastapi import Request

P = ParamSpec("P")
T = TypeVar("T")


def dispatch_message_event(
    message_type: str,
    *,
    dispatcher_param: str = "api_dispatcher",
    request_param: str = "request",
    fastapi_request_param: str = "fastapi_request",
    result_extractor: Callable[[Any], MessageResult] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator that dispatches API message events after route handler execution.

    Automatically extracts the dispatcher, request payload, and recipient from
    the route handler's parameters and result, then fires an API event asynchronously.

    Database Session Support:
        To enable self.db access in process_api_message(), include a FastAPI Request
        parameter in your route. The decorator looks for it in this order:
        1. Parameter named by `fastapi_request_param` (default: "fastapi_request")
        2. Any parameter that is a FastAPI Request instance

    Args:
        message_type: Type of message for the event (e.g., "text", "image", "button")
        dispatcher_param: Name of the dispatcher parameter in the route function
        request_param: Name of the Pydantic request model containing recipient and payload
        fastapi_request_param: Name of the FastAPI Request parameter for DB access
        result_extractor: Optional function to extract MessageResult from return value

    Returns:
        Decorated async function that dispatches events after execution

    Example:
        @router.post("/send-text")
        @dispatch_message_event("text")
        async def send_text_message(
            request: BasicTextMessage,
            fastapi_request: Request,  # Enables self.db in process_api_message
            messenger: IMessenger = Depends(get_whatsapp_messenger),
            api_dispatcher: APIEventDispatcher | None = Depends(get_api_event_dispatcher),
        ) -> MessageResult:
            result = await messenger.send_text(...)
            return result
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Execute the original route handler
            result = await func(*args, **kwargs)

            # Extract dispatcher from kwargs
            dispatcher: APIEventDispatcher | None = kwargs.get(dispatcher_param)
            if dispatcher is None:
                return result

            # Extract Pydantic request model from kwargs (for payload/recipient)
            request_obj = kwargs.get(request_param)
            if request_obj is None:
                return result

            # Extract FastAPI Request for DB session injection
            from fastapi import Request as FastAPIRequest

            fastapi_request: FastAPIRequest | None = kwargs.get(fastapi_request_param)
            if fastapi_request is None:
                # Try to find Request by type in kwargs
                for value in kwargs.values():
                    if isinstance(value, FastAPIRequest):
                        fastapi_request = value
                        break

            # Extract MessageResult (either directly or via extractor)
            message_result: MessageResult
            if result_extractor is not None:
                message_result = result_extractor(result)
            elif isinstance(result, MessageResult):
                message_result = result
            else:
                return result

            # Extract payload and recipient from Pydantic request model
            request_payload: dict = (
                request_obj.model_dump() if hasattr(request_obj, "model_dump") else {}
            )
            recipient: str = getattr(request_obj, "recipient", "")

            # Create and dispatch event asynchronously (fire-and-forget)
            # Pass FastAPI Request to enable DB session injection in handler
            event = APIMessageEvent(
                message_type=message_type,
                message_id=message_result.message_id,
                recipient=recipient,
                request_payload=request_payload,
                response_success=message_result.success,
                response_error=message_result.error,
                meta_response=getattr(message_result, "raw_response", None),
                tenant_id=get_current_tenant_context() or "unknown",
                owner_id=get_current_owner_context(),
            )
            asyncio.create_task(dispatcher.dispatch(event, fastapi_request))

            return result

        return wrapper

    return decorator


def fire_api_event(
    dispatcher: APIEventDispatcher | None,
    message_type: str,
    result: MessageResult,
    request_payload: dict,
    recipient: str,
    fastapi_request: "Request | None" = None,
) -> None:
    """
    Fire API event in background without awaiting.

    Alternative to the decorator for cases where more control is needed.
    This is a synchronous function that creates an async task internally.

    Database Session Support:
        Pass the FastAPI `fastapi_request` parameter to enable self.db access
        in process_api_message() handlers. Without it, self.db will be None.

    Args:
        dispatcher: API event dispatcher (skips if None)
        message_type: Type of message for the event
        result: MessageResult from the messenger operation
        request_payload: Original API request payload
        recipient: Recipient phone number
        fastapi_request: FastAPI Request for database session access (recommended)
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
    asyncio.create_task(dispatcher.dispatch(event, fastapi_request))
