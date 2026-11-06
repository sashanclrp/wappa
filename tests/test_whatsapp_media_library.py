"""WhatsAppMediaLibrary honours ``mime_type`` on upload and ``max_bytes`` on download."""

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from wappa.domain.interfaces.conversation_capabilities import ReadOutcome
from wappa.domain.interfaces.media_library import MediaFamily
from wappa.domain.models.media_result import MediaDownloadResult, MediaInfoResult
from wappa.domain.results import OperationOutcome
from wappa.messaging.meta.graph import GraphResponse, MetaGraphError
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)
from wappa.messaging.whatsapp.media_library import WhatsAppMediaLibrary
from wappa.schemas.core.types import PlatformType


async def _chunks(data: bytes, size: int = 512):
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _library(body: bytes) -> WhatsAppMediaLibrary:
    client = MagicMock()
    client.url_builder.get_media_url.return_value = "https://graph.example/media"
    client.post_request = AsyncMock(return_value={"id": "wa-media-1"})

    @asynccontextmanager
    async def stream_get(url: str):
        response = MagicMock()
        response.status_code = 200
        response.headers = {"content-type": "audio/ogg"}  # no content-length
        response.aiter_bytes = lambda chunk_size=8192: _chunks(body)
        yield response

    client.stream_get = stream_get
    handler = WhatsAppMediaHandler(
        client=client, inbox_id="555", media_download_client=MagicMock()
    )
    handler.get_media_info = AsyncMock(  # type: ignore[method-assign]
        return_value=MediaInfoResult(
            platform=PlatformType.WHATSAPP,
            success=True,
            media_id="m1",
            url="https://cdn.example/m1",
        )
    )
    return WhatsAppMediaLibrary(handler, "555")


async def test_upload_passes_the_explicit_mime_type(tmp_path: Path) -> None:
    library = _library(b"")
    source = tmp_path / "voice.bin"  # no suffix a MIME guess could use
    source.write_bytes(b"ogg")

    result = await library.upload(source, MediaFamily.AUDIO, mime_type="audio/ogg")

    assert result.success and result.media_id == "wa-media-1"
    sent = library._handler.client.post_request.await_args.kwargs
    assert sent["payload"]["type"] == "audio/ogg"


async def test_download_is_bounded_by_max_bytes() -> None:
    library = _library(b"x" * 2048)

    whole = await library.download("m1")
    bounded = await library.download("m1", max_bytes=1024)

    assert whole.found and whole.value is not None and whole.value.size == 2048
    assert bounded.outcome is ReadOutcome.REJECTED
    assert bounded.error_code == "SIZE"


@pytest.mark.parametrize(
    ("error_code", "outcome"),
    [
        ("INVALID_RESPONSE", ReadOutcome.NOT_FOUND),
        ("MEDIA_URL_MISSING", ReadOutcome.NOT_FOUND),
        ("HTTP_400", ReadOutcome.NOT_FOUND),
        ("HTTP_404", ReadOutcome.NOT_FOUND),
        ("HTTP_401", ReadOutcome.ACCESS_DENIED),
        ("HTTP_403", ReadOutcome.ACCESS_DENIED),
        ("HTTP_410", ReadOutcome.REJECTED),
        ("HTTP_500", ReadOutcome.UNAVAILABLE),
        ("MEDIA_INFO_FAILED", ReadOutcome.UNAVAILABLE),
        ("DOWNLOAD_FAILED", ReadOutcome.UNAVAILABLE),
    ],
)
async def test_download_failure_says_whether_a_retry_can_help(
    error_code: str, outcome: ReadOutcome
) -> None:
    handler = MagicMock()
    handler.get_media_as_bytes = AsyncMock(
        return_value=MediaDownloadResult(
            platform=PlatformType.WHATSAPP,
            success=False,
            error="boom",
            error_code=error_code,
        )
    )

    result = await WhatsAppMediaLibrary(handler, "555").download("m1")

    assert result.outcome is outcome
    assert result.error_code == error_code


def _info_failing_library(error: Exception) -> WhatsAppMediaLibrary:
    client = MagicMock()
    client.get_request = AsyncMock(side_effect=error)
    handler = WhatsAppMediaHandler(
        client=client, inbox_id="555", media_download_client=MagicMock()
    )
    return WhatsAppMediaLibrary(handler, "555")


def _graph_error(status: int) -> MetaGraphError:
    """What WhatsAppClient raises after MetaGraphClient classified the call."""
    server = status >= 500
    return MetaGraphError(
        GraphResponse(
            outcome=OperationOutcome.INDETERMINATE
            if server
            else OperationOutcome.REJECTED,
            status_code=status,
            error_code="INDETERMINATE" if server else str(status),
            error="graph error",
        )
    )


@pytest.mark.parametrize(
    ("error", "outcome", "error_code"),
    [
        (_graph_error(400), ReadOutcome.NOT_FOUND, "HTTP_400"),
        (_graph_error(404), ReadOutcome.NOT_FOUND, "HTTP_404"),
        (_graph_error(401), ReadOutcome.ACCESS_DENIED, "HTTP_401"),
        (_graph_error(403), ReadOutcome.ACCESS_DENIED, "HTTP_403"),
        (_graph_error(503), ReadOutcome.UNAVAILABLE, "HTTP_503"),
        (httpx.ReadTimeout("slow"), ReadOutcome.UNAVAILABLE, "MEDIA_INFO_FAILED"),
        (httpx.ConnectError("down"), ReadOutcome.UNAVAILABLE, "MEDIA_INFO_FAILED"),
    ],
)
async def test_a_media_info_failure_keeps_its_cause(
    error: Exception, outcome: ReadOutcome, error_code: str
) -> None:
    result = await _info_failing_library(error).download("dead")

    assert result.outcome is outcome
    assert result.error_code == error_code
