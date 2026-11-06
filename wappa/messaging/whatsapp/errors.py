"""WhatsApp native errors as ``MessageResult`` fields, and the Platform-only codes."""

from __future__ import annotations

from logging import Logger

from wappa.core.logging.logger import ContextLogger
from wappa.domain.interfaces.session_provider import (
    HTTPSessionClosedError,
    RuntimeDrainingError,
)
from wappa.domain.results import MessageResult
from wappa.messaging.meta.graph import MetaGraphError
from wappa.resilience.rate_limits import RateLimitedError
from wappa.schemas.core.recipient import BSUID_ERROR_TAG
from wappa.schemas.core.types import PlatformType

# WhatsApp API error codes
ERROR_CODE_BSUID_NOT_SUPPORTED = 131062

# The shared code for "the outcome is unknown" (``message_outcome`` reads it).
INDETERMINATE = "INDETERMINATE"

# Meta rejected the Delivery Address itself, synchronously and before any
# delivery, so trying the User's next known address can neither duplicate a
# message nor be pointless (ADR-0022):
# - 131030: recipient not in a test number's allow-list (allow-lists hold phones).
# - BSUID_ERROR_TAG (Meta 131062): this message type cannot go to a BSUID.
# Window (131047), rate limit (131056), content (131051), undeliverable
# (131026), timeouts and 5xx are deliberately absent.
ADDRESS_REJECTION_CODES: frozenset[str] = frozenset({"131030", BSUID_ERROR_TAG})


def is_authentication_error(error: Exception) -> bool:
    """Meta refused the token: HTTP 401 or Graph code 190."""
    return isinstance(error, MetaGraphError) and (
        error.status_code == 401 or error.code == "190"
    )


def is_bsuid_unsupported_error(error: Exception) -> bool:
    # Only Meta's structured error code counts. Matching the number in free
    # text could tag a timeout as an address rejection and trigger a
    # fallback send (ADR-0022).
    return isinstance(error, MetaGraphError) and error.code == str(
        ERROR_CODE_BSUID_NOT_SUPPORTED
    )


def handle_whatsapp_error(
    error: Exception,
    operation: str,
    recipient: str,
    inbox_id: str,
    logger: Logger | ContextLogger,
    extra_context: str | None = None,
    include_traceback: bool = False,
) -> MessageResult:
    if isinstance(error, RateLimitedError):
        # Nothing was delivered; the client already logged the limit.
        return MessageResult(
            success=False,
            error=f"Could not {operation}: {error}",
            error_code=error.code,
            retry_after=error.retry_after,
            recipient=recipient,
            platform=PlatformType.WHATSAPP,
            inbox_id=inbox_id,
        )
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
    )


def _classify_transport_error(error: Exception) -> tuple[str, str]:
    """Return a stable code and caller-safe message for transport failures."""
    if isinstance(error, (RuntimeDrainingError, HTTPSessionClosedError)):
        return (
            "runtime_unavailable",
            "The outbound runtime is not accepting transport calls.",
        )
    if isinstance(error, MetaGraphError):
        # Classified once by the shared Meta transport (ADR-0029).
        if error.indeterminate:
            return (
                INDETERMINATE,
                "The messaging platform outcome could not be determined.",
            )
        code = error.code or f"http_{error.status_code}"
        return code, "The messaging platform rejected the request."
    if isinstance(error, ValueError):
        return "invalid_template_request", "The messaging request is invalid."
    return (
        INDETERMINATE,
        "The messaging platform outcome could not be determined.",
    )
