"""One send-route helper and one failure mapper for every Platform (08-04).

Send routes build their target with :func:`direct_target` and are decorated
with :func:`map_send_errors`, which owns every status a send can answer:
``UnsupportedOperationError`` → 501, ``ValueError`` (a local rule violation,
raised before any Platform call) → 400, any other exception → 500, and a
failed result → the status its ``error_code`` maps to (default 400). A result
stopped by a Meta rate limit (``retry_after`` set) answers 429 with a
``Retry-After`` header.
"""

import math
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import Protocol

from fastapi import HTTPException

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.messaging_targets import (
    DeliveryAddresses,
    DirectMessage,
    UnsupportedOperationError,
)
from wappa.domain.models.media_result import MediaUploadResult
from wappa.domain.results import MessageResult
from wappa.schemas.core.recipient import BSUID_ERROR_TAG

# Error code to HTTP status code mapping
ERROR_CODE_MAPPING: dict[str, int] = {
    # Content size errors (413 Payload Too Large)
    "FILE_SIZE_EXCEEDED": 413,
    # Validation errors (400 Bad Request)
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


def raise_if_rate_limited(retry_after: float | None, detail: str | None) -> None:
    """429 + ``Retry-After`` when a Meta rate limit stopped the call."""
    if retry_after is None:
        return
    raise HTTPException(
        status_code=429,
        detail=detail or "Meta rate limit; retry later",
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def raise_for_failed_result(
    result: MessageResult | MediaUploadResult,
    operation_name: str,
    error_code_groups: Mapping[tuple[str, ...], int] | None = None,
) -> None:
    if result.success:
        return
    raise_if_rate_limited(result.retry_after, result.error)

    if error_code_groups and result.error_code:
        for error_codes, status_code in error_code_groups.items():
            if result.error_code in error_codes:
                raise HTTPException(status_code=status_code, detail=result.error)

    status_code = map_error_to_status(result.error_code)
    raise HTTPException(status_code=status_code, detail=result.error)


class _Addressed(Protocol):
    @property
    def recipient(self) -> str: ...


def direct_target(messenger: IMessenger, request: _Addressed) -> DirectMessage:
    """The request's User on the messenger's own Inbox.

    ``request.addresses`` (``DeliveryRequest``) follows ``recipient`` in
    delivery order; a request without it addresses ``recipient`` alone.
    """
    return DirectMessage(
        inbox_ref=InboxRef(platform=messenger.platform, inbox_id=messenger.inbox_id),
        addresses=DeliveryAddresses.of(
            request.recipient, *getattr(request, "addresses", ())
        ),
    )


def map_send_errors[**P, R](
    operation_name: str,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Map a send route's exceptions and failed result onto HTTP statuses.

    Put it above ``@dispatch_message_event`` so the API event still records
    a failed result before the route answers with its error status.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = await func(*args, **kwargs)
            except HTTPException:
                raise
            except UnsupportedOperationError as e:  # not on this Platform
                raise HTTPException(status_code=501, detail=str(e)) from e
            except ValueError as e:  # rejected locally, before any Platform call
                raise HTTPException(status_code=400, detail=str(e)) from e
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"{operation_name} failed: {type(e).__name__}: {e}",
                ) from e
            if isinstance(result, MessageResult | MediaUploadResult):
                raise_for_failed_result(result, operation_name)
            return result

        return wrapper

    return decorator
