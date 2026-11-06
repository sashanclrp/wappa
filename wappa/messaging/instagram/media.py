"""Instagram media constraints and a credential-free attachment downloader.

Outbound limits come from the Instagram messaging guide (Graph v26.0,
fetched 2026-11-03, rechecked 2026-11-06): image png/jpeg/gif ≤ 8 MB; audio
aac/m4a/wav/mp4, video mp4/ogg/avi/mov/webm and file pdf ≤ 25 MB. The guide
states no URL scheme and no file-name rule, so an http(s) URL passes through
(as on WhatsApp) and an upload name is transliterated to ASCII. The live
format matrix (2026-11-06) adds static WebP **by URL** (it renders), while
the attachment upload endpoint answers a WebP with HTTP 500 ("unknown
error", code 1), so a WebP upload is refused before I/O; an animated WebP
renders only its first frame (GIF animates).

Inbound attachment URLs are signed Meta CDN URLs
(``lookaside.fbsbx.com/ig_messaging_cdn/...``) that may expire within minutes.
They are fetched *without* any Platform bearer, only from Meta CDN hosts,
over HTTPS, with bounded redirects, time and size.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

import httpx

from wappa.domain.interfaces.conversation_capabilities import (
    MediaBytes,
    ReadOutcome,
    ReadResult,
)
from wappa.domain.media_probe import probe

MB = 1024 * 1024

CONVERT_HINT = "convert it before sending (Wappa does not convert media)"


@dataclass(frozen=True, slots=True)
class MediaRule:
    wire_type: str
    extensions: frozenset[str]
    max_bytes: int


MEDIA_RULES: dict[str, MediaRule] = {
    "image": MediaRule(
        "image", frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"}), 8 * MB
    ),
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
    ".webp": "image/webp",
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


def mime_for(name: str) -> str:
    return _MIME_BY_SUFFIX.get(Path(name).suffix.lower(), "application/octet-stream")


def upload_name(
    filename: str | None, mime_type: str | None, *, path: Path | None = None
) -> str:
    """The file name an upload goes out with, before ASCII transliteration.

    ``filename`` wins; a ``path`` upload falls back to the file's own name and
    lends its suffix to a ``filename`` without one; for bytes a known
    ``mime_type`` lends its suffix instead. Instagram's rules key off the
    suffix, so bytes need a suffixed ``filename`` or a ``mime_type``
    Instagram knows (``upload`` plus its suffix when there is no name).
    """
    suffix = next((k for k, v in _MIME_BY_SUFFIX.items() if v == mime_type), None)
    if filename:
        name = PurePosixPath(filename.replace("\\", "/")).name
        if not PurePosixPath(name).suffix:
            name += path.suffix if path is not None else suffix or ""
        return name
    if path is not None:
        return path.name
    if suffix is None:
        raise ValueError("Instagram byte uploads need a filename or a known mime_type")
    return f"upload{suffix}"


def ascii_name(name: str) -> str:
    """Transliterate a file name to ASCII, keeping its extension.

    ``"Reseña año.pdf"`` → ``"Resena ano.pdf"``; characters with no ASCII
    form become ``_``, and an empty stem becomes ``file``.
    """
    path = PurePosixPath(name)

    def fold(text: str) -> str:
        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
        return re.sub(r"[^A-Za-z0-9._ ()-]+", "_", plain.decode()).strip()

    return (fold(path.stem) or "file") + fold(path.suffix)


# Formats Instagram renders by URL but its upload endpoint fails (HTTP 500).
URL_ONLY: dict[str, frozenset[str]] = {"image": frozenset({".webp"})}


def validate_upload(name: str, size: int, family: str) -> MediaRule:
    rule = MEDIA_RULES[family]
    suffix = PurePosixPath(name).suffix
    if suffix.lower() in URL_ONLY.get(family, frozenset()):
        raise ValueError(
            f"Instagram renders a {suffix} {family} sent by URL, but its upload "
            "endpoint fails on it (HTTP 500); send it by URL, or upload a PNG or "
            f"JPEG ({CONVERT_HINT})"
        )
    if suffix.lower() not in rule.extensions:
        raise ValueError(
            f"Instagram {family} supports {sorted(rule.extensions)}, not "
            f"{suffix or 'no extension'}; a file must already be in an accepted "
            f"format ({CONVERT_HINT}), or send it by URL to share it as a link"
        )
    if size > rule.max_bytes:
        raise ValueError(
            f"Instagram {family} is {size} bytes; limit is {rule.max_bytes} "
            "(compress it before sending; Wappa does not convert media)"
        )
    return rule


def check_image_content(data: bytes) -> None:
    """Refuse WebP content under another name: an animated WebP shows only its
    first frame, and the upload endpoint fails on any WebP (HTTP 500)."""
    found = probe(data)
    if found.mime == "image/webp" and not found.animated:
        raise ValueError(
            "Instagram's upload endpoint fails on WebP (HTTP 500); send it by "
            "URL, or upload a PNG or JPEG"
        )
    if found.mime == "image/webp" and found.animated:
        raise ValueError(
            "Instagram shows only the first frame of an animated WebP; send the "
            "animation as a GIF (it animates on Instagram) or a static image "
            f"({CONVERT_HINT})"
        )


def validate_local_file(
    path: Path, family: str, *, name: str | None = None
) -> MediaRule:
    """Check a local file under the ``name`` it is uploaded as (default its own)."""
    name = name or path.name
    if not path.is_file():
        validate_upload(name, 0, family)  # a wrong format reports first
        raise ValueError(f"Instagram {family} file does not exist: {path.name}")
    return validate_upload(name, path.stat().st_size, family)


def validate_media_url(url: str) -> str:
    """An absolute http(s) URL; Meta documents no scheme rule, as on WhatsApp."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Instagram media URLs must be absolute http(s) URLs")
    return url


def url_format_accepted(url: str, family: str) -> bool:
    """Whether Instagram takes ``url`` as a ``family`` attachment.

    Judged by the URL path's extension; an extension-less URL passes through,
    since its format cannot be told from its name.
    """
    suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
    return not suffix or suffix in MEDIA_RULES[family].extensions


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
