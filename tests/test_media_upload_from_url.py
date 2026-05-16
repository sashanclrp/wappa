from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)


def _make_handler() -> WhatsAppMediaHandler:
    client = MagicMock()
    client.url_builder.get_media_url.return_value = (
        "https://graph.facebook.com/v25.0/123/media"
    )
    client.post_request = AsyncMock(return_value={"id": "media_id_abc"})
    return WhatsAppMediaHandler(client=client, inbox_id="phone_123")


class _FakeAsyncByteStream:
    """Simulates httpx streaming response.aiter_bytes()."""

    def __init__(self, data: bytes, chunk_size: int = 8192):
        self._data = data
        self._chunk_size = chunk_size
        self._pos = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._pos >= len(self._data):
            raise StopAsyncIteration
        end = min(self._pos + self._chunk_size, len(self._data))
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk


def _mock_response(
    *,
    status_code: int = 200,
    content_type: str = "image/jpeg",
    body: bytes = b"\xff\xd8" * 100,
    content_length: int | None = None,
):
    resp = MagicMock()
    resp.status_code = status_code

    headers = {"content-type": content_type}
    if content_length is not None:
        headers["content-length"] = str(content_length)
    elif body:
        headers["content-length"] = str(len(body))
    resp.headers = headers

    resp.aiter_bytes = lambda chunk_size=8192: _FakeAsyncByteStream(body, chunk_size)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return resp, ctx


def _mock_client(response_ctx):
    client = MagicMock()
    client.stream = MagicMock(return_value=response_ctx)

    client_ctx = AsyncMock()
    client_ctx.__aenter__ = AsyncMock(return_value=client)
    client_ctx.__aexit__ = AsyncMock(return_value=False)
    return client_ctx


@pytest.mark.asyncio
async def test_upload_from_url_success():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(content_type="image/jpeg", body=b"\xff\xd8" * 50)
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url(
            "https://cdn.example.com/photo.jpg"
        )

    assert result.success is True
    assert result.media_id == "media_id_abc"
    assert result.mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_upload_from_url_no_auth_headers():
    """The download client must NOT carry any Authorization header."""
    handler = _make_handler()
    _resp, resp_ctx = _mock_response()
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ) as mock_cls:
        await handler.upload_media_from_url("https://cdn.example.com/photo.jpg")
        call_kwargs = mock_cls.call_args
        if "headers" in (call_kwargs.kwargs if call_kwargs else {}):
            headers = call_kwargs.kwargs["headers"]
            assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_download_failure_returns_error():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(status_code=404)
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url("https://cdn.example.com/gone.jpg")

    assert result.success is False
    assert result.error_code == "DOWNLOAD_FAILED"


@pytest.mark.asyncio
async def test_missing_content_type_returns_error():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(content_type="application/octet-stream")
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url("https://cdn.example.com/blob")

    assert result.success is False
    assert result.error_code == "MIME_TYPE_UNKNOWN"


@pytest.mark.asyncio
async def test_unsupported_mime_type_returns_error():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(content_type="application/zip")
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url(
            "https://cdn.example.com/archive.zip"
        )

    assert result.success is False
    assert result.error_code == "MIME_TYPE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_file_size_exceeded_via_content_length():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(
        content_type="image/jpeg",
        body=b"x",
        content_length=10 * 1024 * 1024,
    )
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url("https://cdn.example.com/huge.jpg")

    assert result.success is False
    assert result.error_code == "FILE_SIZE_EXCEEDED"


@pytest.mark.asyncio
async def test_file_size_exceeded_during_streaming():
    handler = _make_handler()
    oversized_body = b"x" * (6 * 1024 * 1024)
    _resp, resp_ctx = _mock_response(
        content_type="image/jpeg",
        body=oversized_body,
        content_length=None,
    )
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url("https://cdn.example.com/huge.jpg")

    assert result.success is False
    assert result.error_code == "FILE_SIZE_EXCEEDED"


@pytest.mark.asyncio
async def test_filename_gets_extension_from_mime():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response(content_type="image/png", body=b"\x89PNG" * 10)
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ):
        result = await handler.upload_media_from_url(
            "https://cdn.example.com/photo",
            filename="header_image",
        )

    assert result.success is True
    handler.client.post_request.assert_called_once()
    call_kwargs = handler.client.post_request.call_args
    files = call_kwargs.kwargs.get("files") or call_kwargs[1].get("files")
    uploaded_filename = files["file"][0]
    assert uploaded_filename == "header_image.png"


@pytest.mark.asyncio
async def test_custom_timeout_is_applied():
    handler = _make_handler()
    _resp, resp_ctx = _mock_response()
    client_ctx = _mock_client(resp_ctx)

    with patch(
        "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
        return_value=client_ctx,
    ) as mock_cls:
        await handler.upload_media_from_url(
            "https://cdn.example.com/photo.jpg",
            timeout=30.0,
        )
        call_kwargs = mock_cls.call_args
        timeout_obj = call_kwargs.kwargs.get("timeout")
        assert timeout_obj is not None
        assert timeout_obj.read == 30.0
