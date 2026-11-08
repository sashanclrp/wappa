"""Neutral error categories, independent of retry policy and native error codes."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ErrorCategory(StrEnum):
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    MESSAGING_WINDOW = "messaging_window"
    ADDRESS_REJECTION = "address_rejection"
    RATE_LIMIT = "rate_limit"
    UNKNOWN_OUTCOME = "unknown_outcome"
    OTHER = "other"


class ErrorEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    platform_code: str | None = None
    platform_subcode: str | None = None
    http_status: int | None = None
    category: ErrorCategory = ErrorCategory.OTHER
    # None means unknown, not permission to retry a send.
    retry_safe: bool | None = None
    temporary: bool | None = None


def meta_error_evidence(
    code: str | int | None,
    *,
    indeterminate: bool = False,
    rate_limited: bool = False,
    http_status: int | None = None,
    retry_safe: bool | None = None,
) -> ErrorEvidence:
    """Map documented Meta codes rather than HTTP-like numeric ranges."""
    head, _, sub = str(code or "").partition("/")
    category = ErrorCategory.OTHER
    if indeterminate:
        category = ErrorCategory.UNKNOWN_OUTCOME
    elif (
        rate_limited
        or http_status == 429
        or head
        in {
            "4",
            "17",
            "32",
            "613",
            "80007",
            "130429",
            "131048",
            "131056",
        }
    ):
        category = ErrorCategory.RATE_LIMIT
    elif head in {"190", "102"} or http_status == 401:
        category = ErrorCategory.AUTHENTICATION
    elif head == "131047" or (head == "10" and sub in {"2018278", "2534022"}):
        category = ErrorCategory.MESSAGING_WINDOW
    elif (head, sub) in {("100", "2534014"), ("200", "1545041")} or head == "551":
        category = ErrorCategory.ADDRESS_REJECTION
    elif head in {"10", "200", "131005"} or http_status == 403:
        category = ErrorCategory.PERMISSION
    elif head in {"131030", "131062"}:
        category = ErrorCategory.ADDRESS_REJECTION
    return ErrorEvidence(
        platform_code=head or None,
        platform_subcode=sub or None,
        http_status=http_status,
        category=category,
        retry_safe=False if indeterminate else retry_safe,
        temporary=True
        if category is ErrorCategory.RATE_LIMIT or http_status in {500, 502, 503, 504}
        else None,
    )
