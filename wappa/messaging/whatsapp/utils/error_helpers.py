from logging import Logger

import httpx

from wappa.core.logging.logger import ContextLogger
from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
)
from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.resilience import is_transient_http_error
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

    if isinstance(error, httpx.HTTPStatusError):
        return _platform_error_code(error.response) == str(
            ERROR_CODE_BSUID_NOT_SUPPORTED
        )
    return str(ERROR_CODE_BSUID_NOT_SUPPORTED) in str(error)


def handle_whatsapp_error(
    error: Exception,
    operation: str,
    recipient: str,
    inbox_id: str,
    logger: Logger | ContextLogger,
    extra_context: str | None = None,
    include_traceback: bool = False,
) -> MessageResult:
    if is_authentication_error(error):
        logger.error(f"CRITICAL: WhatsApp Authentication Failed - Cannot {operation}!")
        logger.error(f"Check WhatsApp access token for inbox {inbox_id}")

    error_code, safe_error = _classify_transport_error(error)
    if is_bsuid_unsupported_error(error):
        logger.warning(
            f"BSUID Recipient Error: Message type does not support BSUID recipients. "
            f"Use a phone number transport for recipient {recipient}"
        )
        error_code = BSUID_ERROR_TAG
        safe_error = "The recipient identity is not supported for this message type."

    error_message = f"Failed to {operation} to {recipient}: {error}"
    if extra_context:
        error_message = f"{error_message} - {extra_context}"

    logger.error(error_message, exc_info=include_traceback)

    return MessageResult(
        success=False,
        error=safe_error,
        error_code=error_code,
        recipient=recipient,
        recipient_bsuid=None,
        recipient_phone=None,
        platform=PlatformType.WHATSAPP,
        inbox_id=inbox_id,
        api_response=None,
    )


def _classify_transport_error(error: Exception) -> tuple[str, str]:
    """Return a stable code and caller-safe message for transport failures."""
    if isinstance(error, (RuntimeDrainingError, HTTPSessionClosedError)):
        return (
            "runtime_unavailable",
            "The outbound runtime is not accepting transport calls.",
        )
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        platform_code = _platform_error_code(error.response)
        code = platform_code or f"http_{status}"
        return code, "The messaging platform rejected the request."
    if is_transient_http_error(error):
        return (
            "platform_outcome_indeterminate",
            "The messaging platform outcome could not be determined.",
        )
    if isinstance(error, ValueError):
        return "invalid_template_request", "The messaging request is invalid."
    return (
        "platform_outcome_indeterminate",
        "The messaging platform outcome could not be determined.",
    )


def _platform_error_code(response: httpx.Response) -> str | None:
    """Extract only Meta's bounded machine error code from an HTTP response."""
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    value = error.get("code") if isinstance(error, dict) else None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.isdigit():
        return value[:32]
    return None
