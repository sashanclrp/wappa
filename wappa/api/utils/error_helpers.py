"""
Error handling utilities for WhatsApp API routes.

Provides centralized error handling to eliminate code duplication across route handlers.
Follows DRY principle by extracting common error mapping and response patterns.
"""

from collections.abc import Sequence

from fastapi import HTTPException

# Error code to HTTP status code mapping
# Organized by error category for maintainability
ERROR_CODE_MAPPING: dict[str, int] = {
    # Content size errors (413 Payload Too Large)
    "BODY_TOO_LONG": 413,
    "FOOTER_TOO_LONG": 413,
    "BUTTON_TITLE_TOO_LONG": 413,
    "BUTTON_ID_TOO_LONG": 413,
    "BUTTON_TEXT_TOO_LONG": 413,
    "HEADER_TOO_LONG": 413,
    "FILE_SIZE_EXCEEDED": 413,
    # Validation errors (400 Bad Request)
    "INVALID_HEADER_TYPE": 400,
    "INVALID_TEXT_HEADER": 400,
    "INVALID_MEDIA_HEADER": 400,
    "TOO_MANY_SECTIONS": 400,
    "TOO_MANY_ROWS": 400,
    "SECTION_TITLE_TOO_LONG": 400,
    "ROW_TITLE_TOO_LONG": 400,
    "ROW_ID_TOO_LONG": 400,
    "ROW_DESCRIPTION_TOO_LONG": 400,
    "DUPLICATE_ROW_ID": 400,
    "MISSING_REQUIRED_PARAMS": 400,
    "INVALID_URL_FORMAT": 400,
    "INVALID_PARAMETERS": 400,
    "MISSING_PARAMETERS": 400,
    "INVALID_MEDIA_TYPE": 400,
    "MEDIA_NOT_FOUND": 400,
    "INVALID_COORDINATES": 400,
    # Authorization errors (403 Forbidden)
    "TEMPLATE_NOT_FOUND": 403,
    "TEMPLATE_NOT_APPROVED": 403,
    # Media type errors (415 Unsupported Media Type)
    "MIME_TYPE_UNSUPPORTED": 415,
    # Server errors (500 Internal Server Error)
    "TEMPLATE_SEND_FAILED": 500,
    "MEDIA_TEMPLATE_SEND_FAILED": 500,
    "LOCATION_TEMPLATE_SEND_FAILED": 500,
}


def map_error_to_status(error_code: str | None, default_status: int = 400) -> int:
    """Map error code to appropriate HTTP status code.

    Args:
        error_code: The error code from the messaging result
        default_status: Default status code if error code is not mapped

    Returns:
        HTTP status code corresponding to the error code
    """
    if error_code is None:
        return default_status
    return ERROR_CODE_MAPPING.get(error_code, default_status)


def raise_for_failed_result(
    result,
    operation_name: str,
    error_code_groups: dict[Sequence[str], int] | None = None,
) -> None:
    """Raise HTTPException if result indicates failure.

    Centralizes the common pattern of checking result.success and mapping
    error codes to HTTP status codes.

    Args:
        result: Messaging operation result with success, error, and error_code attributes
        operation_name: Human-readable name of the operation for error messages
        error_code_groups: Optional custom error code to status mapping

    Raises:
        HTTPException: If result.success is False
    """
    if result.success:
        return

    # Use custom error code groups if provided
    if error_code_groups and result.error_code:
        for error_codes, status_code in error_code_groups.items():
            if result.error_code in error_codes:
                raise HTTPException(status_code=status_code, detail=result.error)

    # Fall back to global mapping
    status_code = map_error_to_status(result.error_code)
    raise HTTPException(status_code=status_code, detail=result.error)


def handle_messaging_result(
    result,
    operation_name: str,
    not_found_patterns: Sequence[str] | None = None,
):
    """Handle messaging result with standard error mapping.

    Provides a unified way to handle messaging operation results,
    including special handling for "not found" patterns.

    Args:
        result: Messaging operation result
        operation_name: Name of the operation for error messages
        not_found_patterns: Patterns in error message that indicate 404

    Returns:
        The result if successful

    Raises:
        HTTPException: With appropriate status code if failed
    """
    if result.success:
        return result

    error_lower = (result.error or "").lower()

    # Check for "not found" patterns
    if not_found_patterns:
        for pattern in not_found_patterns:
            if pattern.lower() in error_lower:
                raise HTTPException(status_code=404, detail=result.error)

    # Use standard error code mapping
    status_code = map_error_to_status(result.error_code)
    raise HTTPException(status_code=status_code, detail=result.error)


def map_whatsapp_api_error_to_status(error_message: str) -> int:
    """Map WhatsApp API error message patterns to HTTP status codes.

    Used for specialized routes that receive raw error messages
    instead of structured error codes.

    Args:
        error_message: The error message from WhatsApp API

    Returns:
        Appropriate HTTP status code
    """
    error_lower = error_message.lower()

    if "401" in error_message or "unauthorized" in error_lower:
        return 401
    if "400" in error_message or "invalid" in error_lower:
        return 400
    if "429" in error_message or "rate limit" in error_lower:
        return 429
    if "404" in error_message or "not found" in error_lower:
        return 404

    return 500
