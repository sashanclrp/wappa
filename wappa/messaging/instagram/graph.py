"""Inbox-bound Graph HTTP for Instagram (Unified Login, ``graph.facebook.com``).

One place classifies provider outcomes so every operation reports the same
accepted / rejected / indeterminate semantics. Results never carry the bearer
or raw provider error bodies; a rejection logs Meta's error fields. No
automatic retries: an indeterminate mutation may already have taken effect.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.results import OperationOutcome

logger = get_logger(__name__)

# Meta's error fields worth logging; the body never carries the bearer.
_LOGGED_ERROR_FIELDS = (
    "message",
    "type",
    "code",
    "error_subcode",
    "error_user_title",
    "error_user_msg",
    "fbtrace_id",
)

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


@dataclass(frozen=True, slots=True)
class GraphResponse:
    outcome: OperationOutcome
    status_code: int | None = None
    body: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is OperationOutcome.ACCEPTED

    @property
    def native_code(self) -> int | None:
        if not self.error_code:
            return None
        head = self.error_code.split("/", 1)[0]
        return int(head) if head.isdigit() else None


def _error_code(body: Mapping[str, Any]) -> str | None:
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    sub = error.get("error_subcode")
    if code is None:
        return None
    return f"{code}/{sub}" if sub is not None else str(code)


def describe_error(code: str | None, fallback: str) -> str:
    if code is None:
        return fallback
    head = code.split("/", 1)[0]
    return _KNOWN_ERRORS.get(code) or _KNOWN_ERRORS.get(head) or fallback


class InstagramGraphClient:
    """Authenticated requests for one professional account Inbox."""

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        access_token: SecretStr,
        session_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str,
        graph_base_url: str,
    ) -> None:
        self.inbox_ref = inbox_ref
        self._token = access_token
        self._session_provider = session_provider
        self._base = f"{graph_base_url.rstrip('/')}/{graph_api_version}"

    @property
    def account_id(self) -> str:
        return self.inbox_ref.inbox_id

    def url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        operation: str = "Instagram operation",
        timeout: float | None = None,
    ) -> GraphResponse:
        return await graph_request(
            self._session_provider(),
            self._base,
            path,
            self._token,
            method=method,
            operation=operation,
            json=json,
            params=params,
            data=data,
            files=files,
            timeout=timeout,
        )


def _log_rejection(operation: str, status: int, body: Mapping[str, Any]) -> None:
    """Log Meta's error fields, as WhatsApp logs its raw response.

    Results stay credential-free and carry only the code; the log is where
    an operator reads why Meta refused.
    """
    error = body.get("error")
    summary = (
        {k: error[k] for k in _LOGGED_ERROR_FIELDS if k in error}
        if isinstance(error, Mapping)
        else {}
    )
    logger.error("Meta rejected %s (HTTP %s): %s", operation, status, summary)


async def graph_request(
    client: httpx.AsyncClient,
    base: str,
    path: str,
    token: SecretStr,
    *,
    method: str = "GET",
    operation: str,
    json: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
    files: Mapping[str, Any] | None = None,
    timeout: float | None = None,
) -> GraphResponse:
    """One bearer Graph call, classified as accepted / rejected / indeterminate.

    ``base`` is the versioned Graph root (``https://graph.facebook.com/v26.0``).
    A transport failure, a 5xx, or a 2xx that is not an error-free JSON object
    is ``INDETERMINATE``; any other 4xx is ``REJECTED`` with Meta's error code.
    """
    try:
        response = await client.request(
            method,
            f"{base}/{path.lstrip('/')}",
            json=json,
            params=params,
            data=data,
            files=files,
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
    except httpx.RequestError:
        return GraphResponse(
            outcome=OperationOutcome.INDETERMINATE,
            error_code="INDETERMINATE",
            error=f"{operation} outcome is unknown (transport failure); "
            "do not automatically repeat it",
        )
    try:
        parsed = response.json()
    except ValueError:
        parsed = None
    body = parsed if isinstance(parsed, dict) else {}
    if response.is_success and isinstance(parsed, dict) and "error" not in body:
        return GraphResponse(
            outcome=OperationOutcome.ACCEPTED,
            status_code=response.status_code,
            body=body,
        )
    if response.is_success or response.status_code >= 500:
        return GraphResponse(
            outcome=OperationOutcome.INDETERMINATE,
            status_code=response.status_code,
            error_code="INDETERMINATE",
            error=f"{operation} outcome is unknown "
            f"(HTTP {response.status_code}); do not automatically repeat it",
        )
    code = _error_code(body) or str(response.status_code)
    _log_rejection(operation, response.status_code, body)
    return GraphResponse(
        outcome=OperationOutcome.REJECTED,
        status_code=response.status_code,
        error_code=code,
        error=f"{operation} rejected: "
        + describe_error(code, f"provider error {code}"),
    )
