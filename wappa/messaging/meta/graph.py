"""The Meta Graph API transport every Meta Platform adapter shares.

WhatsApp and Instagram both call ``graph.facebook.com/<version>`` with a
Bearer token and get back one error envelope (``error.code``,
``error_subcode``, ``fbtrace_id``) and the same usage headers. This module is
the single place for everything at that level (ADR-0029):

- the versioned base URL and Bearer auth;
- outcome classification: ``accepted``, ``rejected`` (a 4xx with Meta's
  code), ``indeterminate`` (transport failure, 5xx, a 2xx that is not an
  error-free JSON object: never retried) and ``rate_limited``;
- Meta's error code, parsed once (``meta_error_code``);
- logging Meta's error fields, never the token;
- the shared ``RateLimitGovernor`` (``wappa.resilience.rate_limits``), usage
  headers and rewinding a retried upload.

Platform adapters keep only their URL shapes, payloads and their own error
wording (``describe``). ``MetaGraphClient.request`` returns a
``GraphResponse``; ``MetaGraphClient.call`` raises instead
(``MetaGraphError``, ``RateLimitedError``) for adapters whose handlers map
exceptions to results (WhatsApp).
"""

from __future__ import annotations

import json as jsonlib
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.results import OperationOutcome
from wappa.resilience.rate_limits import (
    RateLimited,
    RateLimitedError,
    RateLimitHit,
    RateTarget,
    rate_governor,
    rate_limit_rule,
    rewind,
    usage_headers,
)

logger = get_logger(__name__)

# Meta's error fields worth logging; the body never carries the bearer.
_LOGGED_ERROR_FIELDS = (
    "message",
    "type",
    "code",
    "error_subcode",
    "error_user_title",
    "error_user_msg",
    "error_data",
    "fbtrace_id",
)

Describe = Callable[[str | None, str], str]


def _plain(code: str | None, fallback: str) -> str:
    return fallback


@dataclass(frozen=True, slots=True)
class GraphResponse:
    """One classified Graph call. ``error`` never carries Meta's raw body."""

    outcome: OperationOutcome
    status_code: int | None = None
    body: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None  # "code" or "code/subcode"
    error: str | None = None
    retry_after: float | None = None  # set with outcome rate_limited
    # With rate_limited: False when blocked locally and Meta was not called.
    meta_called: bool = True
    # Meta's usage headers (x-app-usage, x-business-use-case-usage) only.
    usage: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.outcome is OperationOutcome.ACCEPTED

    @property
    def native_code(self) -> int | None:
        """Meta's top-level ``error.code`` (without the subcode)."""
        head = meta_code_head(self.error_code)
        return int(head) if head and head.isdigit() else None


class MetaGraphError(Exception):
    """A Graph call that was not accepted (rejected or indeterminate)."""

    def __init__(self, response: GraphResponse) -> None:
        super().__init__(response.error or "Meta Graph call failed")
        self.response = response

    @property
    def status_code(self) -> int | None:
        return self.response.status_code

    @property
    def code(self) -> str | None:
        """Meta's top-level code (``"131047"``), without the subcode."""
        return meta_code_head(self.response.error_code)

    @property
    def indeterminate(self) -> bool:
        return self.response.outcome is OperationOutcome.INDETERMINATE


def meta_error_code(body: Mapping[str, Any]) -> str | None:
    """Meta's ``error.code`` (``"code/subcode"`` when a subcode is present)."""
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    sub = error.get("error_subcode")
    if code is None:
        return None
    return f"{code}/{sub}" if sub is not None else str(code)


def meta_code_head(code: str | None) -> str | None:
    return code.split("/", 1)[0] if code else None


def _log_failure(operation: str, status: int, body: Mapping[str, Any]) -> None:
    """Log Meta's error fields: rejections at ERROR, 5xx at WARNING."""
    error = body.get("error")
    summary = (
        {k: error[k] for k in _LOGGED_ERROR_FIELDS if k in error}
        if isinstance(error, Mapping)
        else {}
    )
    if status >= 500:  # Meta's side failed: the outcome is unknown
        logger.warning("Meta failed %s (HTTP %s): %s", operation, status, summary)
    else:
        logger.error("Meta rejected %s (HTTP %s): %s", operation, status, summary)
    if status == 401 or meta_code_head(meta_error_code(body)) == "190":
        logger.error(
            "Meta access token invalid or expired for %s: update the Inbox's token",
            operation,
        )


async def graph_request(
    client: httpx.AsyncClient,
    base: str,
    path: str,
    token: SecretStr | None,
    *,
    method: str = "GET",
    operation: str,
    json: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
    files: Mapping[str, Any] | None = None,
    timeout: float | None = None,
    describe: Describe = _plain,
) -> GraphResponse:
    """One bearer Graph call, classified; no rate-limit governance.

    ``base`` is the versioned Graph root (``https://graph.facebook.com/v26.0``);
    an absolute ``path`` (``https://...``) is used as is. Use
    ``MetaGraphClient.request`` for Inbox calls; this raw form serves calls
    made before an Inbox exists (Unified Login). ``token=None`` sends no
    ``Authorization`` header (the code exchange authenticates by query).
    """
    url = path if "://" in path else f"{base}/{path.lstrip('/')}"
    try:
        response = await client.request(
            method,
            url,
            json=json,
            params=params,
            data=data,
            files=files,
            headers=(
                {"Authorization": f"Bearer {token.get_secret_value()}"}
                if token
                else None
            ),
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
    usage = usage_headers(response.headers)
    if response.is_success and isinstance(parsed, dict) and "error" not in body:
        return GraphResponse(
            outcome=OperationOutcome.ACCEPTED,
            status_code=response.status_code,
            body=body,
            usage=usage,
        )
    if response.is_success or response.status_code >= 500:
        if response.status_code >= 500:
            _log_failure(operation, response.status_code, body)
        return GraphResponse(
            outcome=OperationOutcome.INDETERMINATE,
            status_code=response.status_code,
            body=body,
            error_code="INDETERMINATE",
            error=f"{operation} outcome is unknown "
            f"(HTTP {response.status_code}); do not automatically repeat it",
            usage=usage,
        )
    code = meta_error_code(body) or str(response.status_code)
    _log_failure(operation, response.status_code, body)
    return GraphResponse(
        outcome=OperationOutcome.REJECTED,
        status_code=response.status_code,
        body=body,
        error_code=code,
        error=f"{operation} rejected: " + describe(code, f"provider error {code}"),
        usage=usage,
    )


_MEDIA_LANE = frozenset({"audio", "video"})


def _lane(json: Mapping[str, Any] | None, data: Mapping[str, Any] | None) -> str:
    """``media`` for an audio or video attachment (Instagram's 10/s rate)."""
    message: object = (json or {}).get("message")
    if message is None and data and isinstance(data.get("message"), str):
        try:
            message = jsonlib.loads(data["message"])
        except ValueError:
            message = None
    attachment = message.get("attachment") if isinstance(message, Mapping) else None
    kind = attachment.get("type") if isinstance(attachment, Mapping) else None
    return "media" if kind in _MEDIA_LANE else "default"


class MetaGraphClient:
    """Authenticated, rate-governed Graph calls for one Inbox."""

    def __init__(
        self,
        *,
        inbox_ref: InboxRef,
        access_token: SecretStr,
        session_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str,
        graph_base_url: str,
        describe: Describe = _plain,
    ) -> None:
        self.inbox_ref = inbox_ref
        self._token = access_token
        self._session_provider = session_provider
        self.base = f"{graph_base_url.rstrip('/')}/{graph_api_version}"
        self._describe = describe

    @property
    def account_id(self) -> str:
        return self.inbox_ref.inbox_id

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        operation: str = "Meta Graph call",
        timeout: float | None = None,
    ) -> GraphResponse:
        """One governed call; never raises for a Platform outcome."""
        platform = self.inbox_ref.platform.value
        recipient = (json or {}).get("to")
        target = RateTarget(
            platform,
            self.account_id,
            recipient=recipient if isinstance(recipient, str) else None,
            lane=_lane(json, data),
        )
        governor = rate_governor()

        async def call() -> GraphResponse:
            rewind(files)  # a retried upload must send the file again
            return await graph_request(
                self._session_provider(),
                self.base,
                path,
                self._token,
                method=method,
                operation=operation,
                json=json,
                params=params,
                data=data,
                files=files,
                timeout=timeout,
                describe=self._describe,
            )

        def hit_of(response: GraphResponse) -> RateLimitHit | None:
            regain = governor.observe_usage(target, response.usage)
            if response.outcome is OperationOutcome.REJECTED and rate_limit_rule(
                platform, response.error_code
            ):
                return RateLimitHit(response.error_code or "", regain)
            return None

        outcome = await governor.run(target, call, hit_of)
        if isinstance(outcome, RateLimited):
            return GraphResponse(
                outcome=OperationOutcome.RATE_LIMITED,
                error_code=outcome.code,
                error=f"{operation}: {outcome.error}",
                retry_after=outcome.retry_after,
                meta_called=outcome.called,
            )
        return outcome

    @asynccontextmanager
    async def stream(
        self, url: str, params: Mapping[str, Any] | None = None
    ) -> AsyncIterator[httpx.Response]:
        """Authenticated streaming GET of media bytes (Meta's lookaside CDN).

        Not classified or rate-governed: the CDN is not the Graph API and
        answers raw bytes. The caller reads ``response.status_code``.
        """
        try:
            async with self._session_provider().stream(
                "GET",
                url,
                headers={"Authorization": f"Bearer {self._token.get_secret_value()}"},
                params=params,
            ) as response:
                yield response
        except httpx.HTTPError as error:
            logger.error(
                "Media stream failed for %s inbox %s: %s",
                self.inbox_ref.platform.value,
                self.account_id,
                type(error).__name__,
            )
            raise

    async def call(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        operation: str = "Meta Graph call",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """``request`` that returns the accepted body or raises.

        Raises ``RateLimitedError`` for ``rate_limited`` and ``MetaGraphError``
        for ``rejected`` / ``indeterminate``.
        """
        response = await self.request(
            method,
            path,
            json=json,
            params=params,
            data=data,
            files=files,
            operation=operation,
            timeout=timeout,
        )
        if response.ok:
            return response.body
        if response.outcome is OperationOutcome.RATE_LIMITED:
            raise RateLimitedError(
                RateLimited(
                    response.error_code or "",
                    response.retry_after or 0.0,
                    called=response.meta_called,
                )
            )
        raise MetaGraphError(response)


__all__ = [
    "GraphResponse",
    "MetaGraphClient",
    "MetaGraphError",
    "graph_request",
    "meta_code_head",
    "meta_error_code",
]
