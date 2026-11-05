"""Instagram media constraints and a credential-free attachment downloader.

Outbound limits come from the Instagram messaging guide (Graph v26.0,
fetched 2026-11-03): image png/jpeg(/gif) ≤ 8 MB; audio aac/m4a/wav/mp4,
video mp4/ogg/avi/mov/webm and file pdf ≤ 25 MB.

Inbound attachment URLs are signed Meta CDN URLs
(``lookaside.fbsbx.com/ig_messaging_cdn/...``) that may expire within minutes.
They are fetched *without* any Platform bearer, only from Meta CDN hosts,
over HTTPS, with bounded redirects, time and size.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from wappa.domain.interfaces.conversation_capabilities import (
    IAttachmentMediaReader,
    MediaBytes,
    ReadOutcome,
    ReadResult,
)

MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class MediaRule:
    wire_type: str
    extensions: frozenset[str]
    max_bytes: int


MEDIA_RULES: dict[str, MediaRule] = {
    "image": MediaRule("image", frozenset({".png", ".jpg", ".jpeg", ".gif"}), 8 * MB),
    "audio": MediaRule("audio", frozenset({".aac", ".m4a", ".wav", ".mp4"}), 25 * MB),
    "video": MediaRule(
        "video", frozenset({".mp4", ".ogg", ".avi", ".mov", ".webm"}), 25 * MB
    ),
    "document": MediaRule("file", frozenset({".pdf"}), 25 * MB),
}

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".ogg": "video/ogg",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
}

ALLOWED_CDN_SUFFIXES: tuple[str, ...] = (
    "fbsbx.com",
    "fbcdn.net",
    "cdninstagram.com",
)


def mime_for(path: Path) -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def validate_local_file(path: Path, family: str) -> MediaRule:
    rule = MEDIA_RULES[family]
    if path.suffix.lower() not in rule.extensions:
        raise ValueError(
            f"Instagram {family} supports {sorted(rule.extensions)}, not "
            f"{path.suffix or 'no extension'}"
        )
    if not path.is_file():
        raise ValueError(f"Instagram {family} file does not exist: {path.name}")
    size = path.stat().st_size
    if size > rule.max_bytes:
        raise ValueError(
            f"Instagram {family} is {size} bytes; limit is {rule.max_bytes}"
        )
    if not path.name.isascii():
        raise ValueError("Instagram attachment file names must be ASCII")
    return rule


def validate_media_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Instagram media URLs must be absolute https URLs")
    return url


def is_allowed_cdn_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    return any(host == s or host.endswith("." + s) for s in ALLOWED_CDN_SUFFIXES)


class InstagramAttachmentReader(IAttachmentMediaReader):
    """Download provider-exposed attachment bytes without credentials."""

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

    async def stream(
        self, url: str, *, max_bytes: int | None = None, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        """Yield bounded chunks; raises ``ValueError`` for rejected sources."""
        limit = max_bytes or self._default_max
        response, problem = await self._open(url)
        if response is None:
            raise ValueError(problem or "attachment source rejected")
        try:
            if not response.is_success:
                raise ValueError(f"attachment source returned {response.status_code}")
            size = 0
            async for chunk in response.aiter_bytes(chunk_size):
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"attachment exceeds {limit} bytes")
                yield chunk
        finally:
            await response.aclose()
