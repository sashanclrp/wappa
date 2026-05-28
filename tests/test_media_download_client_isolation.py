"""Tests: pooled unauthenticated media downloader isolation and lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wappa.core.lifecycle.session_lifecycle import SessionLifecycle
from wappa.domain.interfaces.session_provider import RuntimeDrainingError
from wappa.messaging.whatsapp.handlers.whatsapp_media_handler import (
    WhatsAppMediaHandler,
)


def _make_lifecycle() -> SessionLifecycle:
    client = httpx.AsyncClient()
    return SessionLifecycle(client)


class TestMediaDownloadClientLifecycle:
    def test_lazy_creation(self):
        lifecycle = _make_lifecycle()
        assert lifecycle._media_client is None

    def test_get_creates_client(self):
        lifecycle = _make_lifecycle()
        media_client = lifecycle.get_media_download_client()
        assert media_client is not None
        assert isinstance(media_client, httpx.AsyncClient)

    def test_authenticated_and_download_are_different_instances(self):
        lifecycle = _make_lifecycle()
        session = lifecycle.get_session()
        media_client = lifecycle.get_media_download_client()
        assert session is not media_client

    def test_returns_same_instance_on_repeated_calls(self):
        lifecycle = _make_lifecycle()
        first = lifecycle.get_media_download_client()
        second = lifecycle.get_media_download_client()
        assert first is second

    def test_rejects_during_drain(self):
        lifecycle = _make_lifecycle()
        lifecycle.begin_drain()
        with pytest.raises(RuntimeDrainingError):
            lifecycle.get_media_download_client()

    @pytest.mark.asyncio
    async def test_close_closes_media_client(self):
        lifecycle = _make_lifecycle()
        media_client = lifecycle.get_media_download_client()
        assert not media_client.is_closed

        await lifecycle.close()

        assert media_client.is_closed
        assert lifecycle._media_client is None

    @pytest.mark.asyncio
    async def test_close_without_media_client(self):
        lifecycle = _make_lifecycle()
        await lifecycle.close()
        assert lifecycle._media_client is None

    def test_media_client_has_no_auth_headers(self):
        lifecycle = _make_lifecycle()
        media_client = lifecycle.get_media_download_client()
        assert "Authorization" not in media_client.headers


class TestMediaHandlerPooledClient:
    @pytest.mark.asyncio
    async def test_uses_pooled_client_when_provided(self):
        mock_wa_client = MagicMock()
        pooled = MagicMock(spec=httpx.AsyncClient)

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "image/jpeg", "content-length": "200"}
        resp.aiter_bytes = lambda chunk_size=8192: _fake_stream(b"\xff\xd8" * 100)

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        pooled.stream = MagicMock(return_value=stream_ctx)

        handler = WhatsAppMediaHandler(
            client=mock_wa_client,
            inbox_id="phone_123",
            media_download_client=pooled,
        )

        mock_wa_client.url_builder.get_media_url.return_value = (
            "https://graph.facebook.com/v25.0/123/media"
        )
        mock_wa_client.post_request = AsyncMock(return_value={"id": "media_id_abc"})

        with patch(
            "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient"
        ) as mock_cls:
            result = await handler.upload_media_from_url(
                "https://cdn.example.com/photo.jpg"
            )
            mock_cls.assert_not_called()

        assert result.success is True
        pooled.stream.assert_called_once()
        pooled.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_without_pooled_client(self):
        mock_wa_client = MagicMock()
        mock_wa_client.url_builder.get_media_url.return_value = (
            "https://graph.facebook.com/v25.0/123/media"
        )
        mock_wa_client.post_request = AsyncMock(return_value={"id": "media_id_abc"})

        handler = WhatsAppMediaHandler(
            client=mock_wa_client, inbox_id="phone_123"
        )

        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "image/jpeg", "content-length": "200"}
        resp.aiter_bytes = lambda chunk_size=8192: _fake_stream(b"\xff\xd8" * 100)

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        fallback_client = MagicMock()
        fallback_client.stream = MagicMock(return_value=stream_ctx)
        fallback_client.aclose = AsyncMock()

        with patch(
            "wappa.messaging.whatsapp.handlers.whatsapp_media_handler.httpx.AsyncClient",
            return_value=fallback_client,
        ) as mock_cls:
            result = await handler.upload_media_from_url(
                "https://cdn.example.com/photo.jpg"
            )
            mock_cls.assert_called_once()

        assert result.success is True
        fallback_client.aclose.assert_awaited_once()


class _FakeAsyncIter:
    def __init__(self, data: bytes, chunk_size: int = 8192):
        self._data = data
        self._pos = 0
        self._chunk_size = chunk_size

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._pos >= len(self._data):
            raise StopAsyncIteration
        end = min(self._pos + self._chunk_size, len(self._data))
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk


def _fake_stream(data: bytes):
    return _FakeAsyncIter(data)
