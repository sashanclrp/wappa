"""
WhatsApp error handling utilities.

Provides centralized error handling for WhatsApp messaging operations,
including authentication error detection and standardized error responses.
"""

from logging import Logger

from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.types import PlatformType


def is_authentication_error(error: Exception) -> bool:
    """Check if an exception indicates an authentication failure.

    Args:
        error: The exception to check

    Returns:
        True if the error indicates authentication failure (401/Unauthorized)
    """
    error_str = str(error)
    return "401" in error_str or "Unauthorized" in error_str


def handle_whatsapp_error(
    error: Exception,
    operation: str,
    recipient: str,
    tenant_id: str,
    logger: Logger,
    extra_context: str | None = None,
    include_traceback: bool = False,
) -> MessageResult:
    """Handle WhatsApp API errors with consistent logging and response formatting.

    This helper centralizes error handling for WhatsApp messaging operations,
    providing consistent authentication error detection and logging.

    Args:
        error: The exception that occurred
        operation: Description of the operation that failed (e.g., "send text message")
        recipient: The recipient identifier (phone number or message ID)
        tenant_id: The tenant/phone_number_id for logging context
        logger: Logger instance for error logging
        extra_context: Optional additional context to include in error log
        include_traceback: Whether to include full traceback in log (exc_info=True)

    Returns:
        MessageResult with success=False and appropriate error details
    """
    if is_authentication_error(error):
        logger.error(
            f"CRITICAL: WhatsApp Authentication Failed - Cannot {operation}!"
        )
        logger.error(f"Check WhatsApp access token for tenant {tenant_id}")

    error_message = f"Failed to {operation} to {recipient}: {error}"
    if extra_context:
        error_message = f"{error_message} - {extra_context}"

    logger.error(error_message, exc_info=include_traceback)

    return MessageResult(
        success=False,
        error=str(error),
        recipient=recipient,
        platform=PlatformType.WHATSAPP,
        tenant_id=tenant_id,
    )
