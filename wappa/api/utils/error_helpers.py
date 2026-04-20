from collections.abc import Sequence

from fastapi import HTTPException

from wappa.messaging.whatsapp.utils.error_helpers import BSUID_ERROR_TAG

# Error code to HTTP status code mapping
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
    BSUID_ERROR_TAG: 400,
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
    if error_code is None:
        return default_status
    return ERROR_CODE_MAPPING.get(error_code, default_status)


def raise_for_failed_result(
    result,
    operation_name: str,
    error_code_groups: dict[Sequence[str], int] | None = None,
) -> None:
    if result.success:
        return

    if error_code_groups and result.error_code:
        for error_codes, status_code in error_code_groups.items():
            if result.error_code in error_codes:
                raise HTTPException(status_code=status_code, detail=result.error)

    status_code = map_error_to_status(result.error_code)
    raise HTTPException(status_code=status_code, detail=result.error)


def map_whatsapp_api_error_to_status(error_message: str) -> int:
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
