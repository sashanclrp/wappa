"""Credential-free download of Instagram attachments from Meta CDN hosts.

Inbound attachment URLs are signed Meta CDN URLs
(``lookaside.fbsbx.com/ig_messaging_cdn/...``) that may expire within minutes.
They are fetched *without* any Platform bearer, only from Meta CDN hosts,
over HTTPS, with bounded redirects, time and size.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx

from wappa.domain.interfaces.conversation_capabilities import (
    MediaBytes,
    ReadOutcome,
    ReadResult,
)

from .rules import MB

ALLOWED_CDN_SUFFIXES: tuple[str, ...] = (
    "fbsbx.com",
    "fbcdn.net",
    "cdninstagram.com",
)


def is_allowed_cdn_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    return any(host == s or host.endswith("." + s) for s in ALLOWED_CDN_SUFFIXES)


class InstagramAttachmentReader:
    """Download provider-exposed attachment bytes without credentials.

    Private to ``InstagramMediaLibrary.download``: never sends Platform
    credentials, only fetches https Meta CDN hosts, and bounds redirects, time
    and size.
    """

    def __init__(
        self,
        client_provider: Callable[[], httpx.AsyncClient],
        *,
        default_max_bytes: int = 25 * MB,
        max_redirects: int = 3,
        timeout_seconds: float = 30.0,
        allowed_host: Callable[[str | None], bool] = is_allowed_cdn_host,
    ) -> None:
        self._client_provider = client_provider
        self._default_max = default_max_bytes
        self._max_redirects = max_redirects
        self._timeout = timeout_seconds
        self._allowed_host = allowed_host

    def _check(self, url: str) -> str | None:
        parts = urlsplit(url)
        if parts.scheme != "https":
            return "attachment URL must use https"
        if not self._allowed_host(parts.hostname):
            return "attachment host is not a Meta CDN host"
        return None

    async def _open(self, url: str) -> tuple[httpx.Response | None, str | None]:
        client = self._client_provider()
        current = url
        for _ in range(self._max_redirects + 1):
            problem = self._check(current)
            if problem:
                return None, problem
            request = client.build_request(
                "GET", current, timeout=self._timeout, headers={"Accept": "*/*"}
            )
            response = await client.send(request, stream=True, follow_redirects=False)
            if response.is_redirect:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    return None, "redirect without location"
                current = urljoin(current, location)
                continue
            return response, None
        return None, "too many redirects"

    async def get_bytes(
        self, url: str, *, max_bytes: int | None = None
    ) -> ReadResult[MediaBytes]:
        limit = max_bytes or self._default_max
        try:
            response, problem = await self._open(url)
        except httpx.RequestError:
            return ReadResult(
                outcome=ReadOutcome.UNAVAILABLE,
                error="attachment source timed out or is unreachable",
                error_code="TRANSPORT",
            )
        if response is None:
            return ReadResult(
                outcome=ReadOutcome.REJECTED, error=problem, error_code="SOURCE"
            )
        try:
            if response.status_code in (403, 404, 410):
                return ReadResult(
                    outcome=ReadOutcome.NOT_FOUND,
                    error="attachment expired, deleted or not accessible",
                    error_code=str(response.status_code),
                )
            if not response.is_success:
                return ReadResult(
                    outcome=ReadOutcome.UNAVAILABLE,
                    error=f"attachment source returned HTTP {response.status_code}",
                    error_code=str(response.status_code),
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                return ReadResult(
                    outcome=ReadOutcome.REJECTED,
                    error=f"attachment exceeds {limit} bytes",
                    error_code="SIZE",
                )
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    return ReadResult(
                        outcome=ReadOutcome.REJECTED,
                        error=f"attachment exceeds {limit} bytes",
                        error_code="SIZE",
                    )
                chunks.append(chunk)
            if size == 0:
                return ReadResult(
                    outcome=ReadOutcome.UNAVAILABLE,
                    error="attachment source returned no bytes",
                    error_code="EMPTY",
                )
            content_type = response.headers.get("content-type")
            return ReadResult(
                outcome=ReadOutcome.FOUND,
                value=MediaBytes(
                    content=b"".join(chunks),
                    content_type=content_type.split(";")[0].strip()
                    if content_type
                    else None,
                    size=size,
                    source_host=response.url.host,
                ),
            )
        except httpx.RequestError:
            return ReadResult(
                outcome=ReadOutcome.UNAVAILABLE,
                error="attachment download interrupted",
                error_code="TRANSPORT",
            )
        finally:
            await response.aclose()
