"""
API endpoints for managing user state handlers.

This module provides REST API endpoints for assigning, retrieving, and deleting
state handlers for users. State handlers are stored in cache and used to route
user responses to specific event handlers after messages have been sent.

The state handler API is message-agnostic and can be used after any message
type (template, media, text, interactive, etc.) to assign workflow routing.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from wappa.api.dependencies.cache_dependencies import get_handler_state_service
from wappa.api.models.handler_models import (
    HandlerStateResponse,
    SetHandlerStateRequest,
)
from wappa.api.services.handler_state_service import HandlerStateService

router = APIRouter(prefix="/whatsapp/state-handlers", tags=["WhatsApp State Handlers"])


@router.post(
    "/set",
    response_model=HandlerStateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set State Handler for User",
    description=(
        "Assign a cache state handler to a user. This is message-agnostic "
        "and can be used after any message type has been sent. "
        "Useful for automation workflows that need to route user responses "
        "to specific handlers after message delivery."
    ),
)
async def set_handler_state(
    request: SetHandlerStateRequest,
    handler_service: HandlerStateService = Depends(get_handler_state_service),
) -> HandlerStateResponse:
    """
    Set a state handler for a user via cache.

    This endpoint allows you to assign a state handler to a user AFTER
    any message has been sent (template, media, text, interactive, etc.).

    The handler state is stored in cache with the key pattern:
    `api-handler-{handler_value}` and is scoped to the user's phone number.

    **Example automation workflow:**
    1. Send a template/media message to user
    2. Call this endpoint to assign a handler (e.g., "reschedule_flow")
    3. When user responds, your event dispatcher routes to the handler

    **Request Body:**
    ```json
    {
      "recipient": "+1234567890",
      "handler_config": {
        "handler_value": "reschedule_flow",
        "ttl_seconds": 3600,
        "initial_context": {
          "appointment_id": "12345",
          "original_time": "2024-01-15T10:00:00Z"
        }
      }
    }
    ```

    **Response:**
    ```json
    {
      "success": true,
      "message": "State handler assigned successfully",
      "recipient": "+1234567890",
      "handler_value": "reschedule_flow",
      "cache_key": "api-handler-reschedule_flow",
      "expires_at": "2024-01-15T11:00:00Z"
    }
    ```
    """
    try:
        cache_key, expires_at = await handler_service.set_handler_state(
            recipient=request.recipient,
            handler_value=request.handler_config.handler_value,
            ttl_seconds=request.handler_config.ttl_seconds,
            initial_context=request.handler_config.initial_context,
        )

        return HandlerStateResponse(
            success=True,
            message="State handler assigned successfully",
            recipient=request.recipient,
            handler_value=request.handler_config.handler_value,
            cache_key=cache_key,
            expires_at=expires_at.isoformat(),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set handler state: {str(e)}",
        ) from e


@router.get(
    "/get/{recipient}/{handler_value}",
    summary="Get State Handler for User",
    description="Retrieve the current state handler assigned to a user",
)
async def get_handler_state(
    recipient: str,
    handler_value: str,
    handler_service: HandlerStateService = Depends(get_handler_state_service),
):
    """
    Get handler state for a user.

    Retrieves the state handler configuration for a user if one exists.
    Returns 404 if no handler is found.

    **Path Parameters:**
    - `recipient`: User phone number (e.g., "+1234567890")
    - `handler_value`: Handler identifier (e.g., "reschedule_flow")

    **Response:**
    ```json
    {
      "success": true,
      "recipient": "+1234567890",
      "handler_value": "reschedule_flow",
      "state": {
        "handler_value": "reschedule_flow",
        "recipient": "+1234567890",
        "assigned_at": "2024-01-15T10:00:00Z",
        "expires_at": "2024-01-15T11:00:00Z",
        "appointment_id": "12345",
        "original_time": "2024-01-15T10:00:00Z"
      }
    }
    ```
    """
    state = await handler_service.get_handler_state(recipient, handler_value)

    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No handler state found for {recipient} with handler {handler_value}",
        )

    return {
        "success": True,
        "recipient": recipient,
        "handler_value": handler_value,
        "state": state,
    }


@router.delete(
    "/delete/{recipient}/{handler_value}",
    summary="Delete State Handler for User",
    description="Remove a state handler assignment from a user",
)
async def delete_handler_state(
    recipient: str,
    handler_value: str,
    handler_service: HandlerStateService = Depends(get_handler_state_service),
):
    """
    Delete handler state for a user.

    Removes the state handler assignment for a user. This can be useful
    when a workflow is completed or cancelled.

    **Path Parameters:**
    - `recipient`: User phone number (e.g., "+1234567890")
    - `handler_value`: Handler identifier (e.g., "reschedule_flow")

    **Response:**
    ```json
    {
      "success": true,
      "message": "Handler state deleted successfully",
      "recipient": "+1234567890",
      "handler_value": "reschedule_flow"
    }
    ```
    """
    await handler_service.delete_handler_state(recipient, handler_value)

    return {
        "success": True,
        "message": "Handler state deleted successfully",
        "recipient": recipient,
        "handler_value": handler_value,
    }
