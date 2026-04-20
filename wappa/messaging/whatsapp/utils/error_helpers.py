from logging import Logger

from wappa.core.logging.logger import ContextLogger
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.types import PlatformType

# WhatsApp API error codes
ERROR_CODE_BSUID_NOT_SUPPORTED = 131062
# Tag surfaced on MessageResult.error_code and reused by the API layer's HTTP mapping.
BSUID_ERROR_TAG = "BSUID_RECIPIENT_NOT_SUPPORTED"


def is_authentication_error(error: Exception) -> bool:
    error_str = str(error).lower()
    return "401" in error_str or "unauthorized" in error_str


def is_bsuid_unsupported_error(error: Exception | dict) -> bool:
    if isinstance(error, dict):
        error_code = error.get("code") or error.get("error_code")
        return error_code == ERROR_CODE_BSUID_NOT_SUPPORTED

    return str(ERROR_CODE_BSUID_NOT_SUPPORTED) in str(error)


def handle_whatsapp_error(
    error: Exception,
    operation: str,
    recipient: str,
    tenant_id: str,
    logger: Logger | ContextLogger,
    extra_context: str | None = None,
    include_traceback: bool = False,
) -> MessageResult:
    if is_authentication_error(error):
        logger.error(f"CRITICAL: WhatsApp Authentication Failed - Cannot {operation}!")
        logger.error(f"Check WhatsApp access token for tenant {tenant_id}")

    error_code = None
    if is_bsuid_unsupported_error(error):
        logger.warning(
            f"BSUID Recipient Error: Message type does not support BSUID recipients. "
            f"Use a phone number transport for recipient {recipient}"
        )
        error_code = BSUID_ERROR_TAG

    error_message = f"Failed to {operation} to {recipient}: {error}"
    if extra_context:
        error_message = f"{error_message} - {extra_context}"

    logger.error(error_message, exc_info=include_traceback)

    return MessageResult(
        success=False,
        error=str(error),
        error_code=error_code,
        recipient=recipient,
        platform=PlatformType.WHATSAPP,
        tenant_id=tenant_id,
    )
