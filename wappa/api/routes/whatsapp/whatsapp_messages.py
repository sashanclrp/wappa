"""
WhatsApp messaging API endpoints.

Provides REST API endpoints for WhatsApp messaging operations:
- POST /api/whatsapp/messages/send-text: Send text messages
- POST /api/whatsapp/messages/mark-as-read: Mark messages as read with optional typing

Router configuration:
- Prefix: /whatsapp/messages
- Tags: ["WhatsApp - Messages"]
- Full URL: /api/whatsapp/messages/ (when included with /api prefix)
"""

from fastapi import APIRouter, Depends, HTTPException

from wappa.api.dependencies.whatsapp_dependencies import (
    get_whatsapp_message_factory,
    get_whatsapp_messenger,
)
from wappa.core.logging.logger import get_logger
from wappa.domain.factories.message_factory import MessageFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.messaging.whatsapp.models.basic_models import (
    BasicTextMessage,
    MessageResult,
    ReadStatusMessage,
)

# Create router with WhatsApp Messages configuration
router = APIRouter(
    prefix="/whatsapp/messages",
    tags=["WhatsApp - Messages"],
    responses={
        400: {"description": "Bad Request - Invalid message format"},
        401: {"description": "Unauthorized - Invalid tenant credentials"},
        429: {"description": "Rate Limited - Too many requests"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/send-text",
    response_model=MessageResult,
    summary="Send Text Message",
    description="Send a text message via WhatsApp with optional reply and preview control",
)
async def send_text_message(
    request: BasicTextMessage, messenger: IMessenger = Depends(get_whatsapp_messenger)
) -> MessageResult:
    """Send a text message via WhatsApp.

    Sends a text message through WhatsApp Business API with support for:
    - Reply to existing messages (threading)
    - URL preview control
    - Automatic URL detection and preview handling

    Args:
        request: Text message payload with recipient, content, and options
        messenger: WhatsApp messenger implementation (injected)

    Returns:
        MessageResult with operation status, message ID, and metadata

    Raises:
        HTTPException 400: If message validation fails
        HTTPException 401: If tenant credentials are invalid
        HTTPException 500: If WhatsApp API call fails
    """
    logger = get_logger(__name__)

    try:
        logger.info(f"Sending text message to {request.recipient}")

        result = await messenger.send_text(
            text=request.text,
            recipient=request.recipient,
            reply_to_message_id=request.reply_to_message_id,
            disable_preview=request.disable_preview,
        )

        if result.success:
            logger.info(f"Text message sent successfully: {result.message_id}")
        else:
            logger.error(f"Failed to send text message: {result.error}")

        return result

    except ValueError as e:
        logger.error(f"Validation error sending text message: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error sending text message: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.post(
    "/mark-as-read",
    response_model=MessageResult,
    summary="Mark Message as Read",
    description="Mark a WhatsApp message as read with optional typing indicator",
)
async def mark_message_as_read(
    request: ReadStatusMessage, messenger: IMessenger = Depends(get_whatsapp_messenger)
) -> MessageResult:
    """Mark a WhatsApp message as read with optional typing indicator.

    Marks a message as read through WhatsApp Business API with support for:
    - Simple read receipt (typing=false)
    - Read receipt with typing indicator (typing=true) - Key requirement

    Args:
        request: Read status payload with message ID and typing flag
        messenger: WhatsApp messenger implementation (injected)

    Returns:
        MessageResult with operation status and metadata

    Raises:
        HTTPException 400: If message ID is invalid
        HTTPException 401: If tenant credentials are invalid
        HTTPException 500: If WhatsApp API call fails
    """
    logger = get_logger(__name__)

    try:
        action_desc = "with typing indicator" if request.typing else "without typing"
        logger.info(f"Marking message {request.message_id} as read {action_desc}")

        result = await messenger.mark_as_read(
            message_id=request.message_id,
            typing=request.typing,  # Key requirement: typing boolean support
        )

        if result.success:
            logger.info(f"Message marked as read successfully: {request.message_id}")
        else:
            logger.error(f"Failed to mark message as read: {result.error}")

        return result

    except ValueError as e:
        logger.error(f"Validation error marking message as read: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error marking message as read: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to mark message as read")


@router.get(
    "/limits",
    summary="Get Message Limits",
    description="Get WhatsApp platform-specific message limits and constraints",
)
async def get_message_limits(
    factory: MessageFactory = Depends(get_whatsapp_message_factory),
) -> dict:
    """Get WhatsApp platform-specific message limits.

    Returns current WhatsApp Business API limits for message validation
    including text length limits, media size limits, and interactive message constraints.

    Args:
        factory: WhatsApp message factory (injected)

    Returns:
        Dictionary containing platform-specific limits and constraints
    """
    return factory.get_message_limits()


@router.get(
    "/health",
    summary="Health Check",
    description="Check WhatsApp messaging service health",
)
async def health_check(messenger: IMessenger = Depends(get_whatsapp_messenger)) -> dict:
    """Health check for WhatsApp messaging service.

    Verifies that the WhatsApp messaging service is properly configured
    and ready to handle requests.

    Args:
        messenger: WhatsApp messenger implementation (injected)

    Returns:
        Health status information
    """
    return {
        "status": "healthy",
        "service": "whatsapp-messages",
        "platform": messenger.platform.value,
        "tenant_id": messenger.tenant_id,
        "timestamp": "2025-01-26T00:00:00Z",
    }
