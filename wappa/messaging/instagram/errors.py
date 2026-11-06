"""Instagram error wording and read-failure mapping.

``describe_error`` turns a native Messenger-family error code into a short,
credential-free explanation (the Meta transport calls it for every failure);
``read_failure`` maps a refused or unknown Graph read to a neutral
``ReadResult`` outcome.
"""

from __future__ import annotations

from wappa.domain.interfaces.conversation_capabilities import ReadOutcome, ReadResult
from wappa.domain.results import OperationOutcome
from wappa.messaging.meta.graph import GraphResponse

# Known Messenger-family error codes → short, credential-free explanations.
_KNOWN_ERRORS: dict[str, str] = {
    "10/2534022": "outside the allowed messaging window",
    "10/2018278": "outside the allowed messaging window",
    "10/2018108": "the user cannot receive messages right now",
    "10/1893063": "the account is temporarily restricted",
    "10/2018300": "another app controls this thread",
    "100/2534037": "another app controls this thread",
    "551": "the user is unavailable",
    "551/1545041": "the user is unavailable",
    "200/1545041": "the recipient is not available",
    "200/2534041": "the account owner disabled message access",
    "100/2534014": "no matching Instagram user for this recipient (IGSID required)",
    "100/2534015": "invalid message data",
    "100/2534025": "comment is not valid for a private reply (expired or used)",
    "100/2534029": "the business is blocked from Instagram messaging",
    "100/2018008": "the provider could not fetch the media URL",
    "100/2018047": "attachment type does not match the media",
    "100/2018109": "attachment exceeds the size limit",
    "100/2018294": "video upload timed out",
    "100/2018074": "invalid attachment_id",
    "100/33": "object does not exist or is not accessible",
    "190": "access token is invalid or expired",
    "613/2534040": "rate limit reached",
    "4": "application rate limit reached",
    "2534068": "multi-image sends are not enabled for this account",
}


def describe_error(code: str | None, fallback: str) -> str:
    if code is None:
        return fallback
    head = code.split("/", 1)[0]
    return _KNOWN_ERRORS.get(code) or _KNOWN_ERRORS.get(head) or fallback


def read_failure[T](response: GraphResponse) -> ReadResult[T]:
    code = response.native_code
    if response.outcome in (
        OperationOutcome.INDETERMINATE,
        OperationOutcome.RATE_LIMITED,
    ):
        outcome = ReadOutcome.UNAVAILABLE
    elif response.error_code in ("100/33",) or response.status_code == 404:
        outcome = ReadOutcome.NOT_FOUND
    elif code in (10, 190, 200) or response.status_code in (401, 403):
        outcome = ReadOutcome.ACCESS_DENIED
    else:
        outcome = ReadOutcome.REJECTED
    return ReadResult(
        outcome=outcome,
        error=response.error,
        error_code=response.error_code,
        retry_after=response.retry_after,
    )
