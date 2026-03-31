"""Messenger wrapper that publishes full bot message payloads via SSE."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.messaging_interface import IMessenger
from ...schemas.core.types import PlatformType
from .event_hub import SSEEventHub
from .handlers import publish_sse_event

if TYPE_CHECKING:
    from ...messaging.whatsapp.models.basic_models import MessageResult
    from ...messaging.whatsapp.models.interactive_models import ListSection


class SSEMessengerWrapper(IMessenger):
    """Wrap IMessenger and publish full outgoing bot payloads to SSE."""

    def __init__(
        self,
        *,
        inner: IMessenger,
        event_hub: SSEEventHub,
        tenant: str,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ):
        self._inner = inner
        self._event_hub = event_hub
        self._tenant = tenant
        self._user_id = user_id
        self._metadata = metadata

    def update_metadata(self, **kwargs: Any) -> None:
        """Merge key-value pairs into the wrapper's metadata dict."""
        if self._metadata is None:
            self._metadata = {}
        self._metadata.update(kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the inner messenger for full transparency."""
        return getattr(self._inner, name)

    @property
    def platform(self) -> PlatformType:
        return self._inner.platform

    @property
    def tenant_id(self) -> str:
        return self._inner.tenant_id

    async def _send_with_sse(
        self,
        *,
        message_type: str,
        request_payload: dict[str, Any],
        operation: Awaitable[MessageResult],
    ) -> MessageResult:
        result = await operation

        await publish_sse_event(
            self._event_hub,
            event_type="outgoing_bot_message",
            tenant_id=self._tenant,
            user_id=self._user_id,
            platform=self._inner.platform.value,
            source="bot_messenger",
            payload={
                "message_type": message_type,
                "request": self._to_serializable(request_payload),
                "result": self._to_serializable(result),
            },
            metadata=self._metadata,
        )

        return result

    def _to_serializable(self, value: Any) -> Any:
        """Convert complex payload values into JSON-serializable structures."""
        if isinstance(value, Path):
            return str(value)

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", exclude_none=False)

        if isinstance(value, dict):
            return {
                str(key): self._to_serializable(item) for key, item in value.items()
            }

        if isinstance(value, list | tuple | set):
            return [self._to_serializable(item) for item in value]

        return value

    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="text",
            request_payload={
                "text": text,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
                "disable_preview": disable_preview,
            },
            operation=self._inner.send_text(
                text,
                recipient,
                reply_to_message_id,
                disable_preview,
            ),
        )

    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult:
        return await self._inner.mark_as_read(message_id, typing)

    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="image",
            request_payload={
                "image_source": image_source,
                "recipient": recipient,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_image(
                image_source,
                recipient,
                caption,
                reply_to_message_id,
            ),
        )

    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="video",
            request_payload={
                "video_source": video_source,
                "recipient": recipient,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
            },
            operation=self._inner.send_video(
                video_source,
                recipient,
                caption,
                reply_to_message_id,
                transcript,
            ),
        )

    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="audio",
            request_payload={
                "audio_source": audio_source,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
            },
            operation=self._inner.send_audio(
                audio_source,
                recipient,
                reply_to_message_id,
                transcript,
            ),
        )

    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="document",
            request_payload={
                "document_source": document_source,
                "recipient": recipient,
                "filename": filename,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_document(
                document_source,
                recipient,
                filename,
                caption,
                reply_to_message_id,
            ),
        )

    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="sticker",
            request_payload={
                "sticker_source": sticker_source,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_sticker(
                sticker_source,
                recipient,
                reply_to_message_id,
            ),
        )

    async def send_button_message(
        self,
        buttons: list[dict[str, str]],
        recipient: str,
        body: str,
        header: dict | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="button",
            request_payload={
                "buttons": buttons,
                "recipient": recipient,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_button_message(
                buttons,
                recipient,
                body,
                header,
                footer,
                reply_to_message_id,
            ),
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="list",
            request_payload={
                "sections": sections,
                "recipient": recipient,
                "body": body,
                "button_text": button_text,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_list_message(
                sections,
                recipient,
                body,
                button_text,
                header,
                footer,
                reply_to_message_id,
            ),
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="cta",
            request_payload={
                "button_text": button_text,
                "button_url": button_url,
                "recipient": recipient,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_cta_message(
                button_text,
                button_url,
                recipient,
                body,
                header,
                footer,
                reply_to_message_id,
            ),
        )

    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="text_template",
            request_payload={
                "template_name": template_name,
                "recipient": recipient,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
            operation=self._inner.send_text_template(
                template_name,
                recipient,
                body_parameters,
                language_code,
            ),
        )

    async def send_media_template(
        self,
        template_name: str,
        recipient: str,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="media_template",
            request_payload={
                "template_name": template_name,
                "recipient": recipient,
                "media_type": media_type,
                "media_id": media_id,
                "media_url": media_url,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
            operation=self._inner.send_media_template(
                template_name,
                recipient,
                media_type,
                media_id,
                media_url,
                body_parameters,
                language_code,
            ),
        )

    async def send_location_template(
        self,
        template_name: str,
        recipient: str,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="location_template",
            request_payload={
                "template_name": template_name,
                "recipient": recipient,
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
            operation=self._inner.send_location_template(
                template_name,
                recipient,
                latitude,
                longitude,
                name,
                address,
                body_parameters,
                language_code,
            ),
        )

    async def send_contact(
        self,
        contact: dict,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="contact",
            request_payload={
                "contact": contact,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_contact(contact, recipient, reply_to_message_id),
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="location",
            request_payload={
                "latitude": latitude,
                "longitude": longitude,
                "recipient": recipient,
                "name": name,
                "address": address,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_location(
                latitude,
                longitude,
                recipient,
                name,
                address,
                reply_to_message_id,
            ),
        )

    async def send_location_request(
        self,
        body: str,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_sse(
            message_type="location_request",
            request_payload={
                "body": body,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
            },
            operation=self._inner.send_location_request(
                body,
                recipient,
                reply_to_message_id,
            ),
        )
