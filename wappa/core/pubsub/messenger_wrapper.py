from __future__ import annotations

import logging
import warnings
from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.interfaces.messaging_interface import IMessenger
from ...schemas.core.types import PlatformType
from .handlers import publish_notification

if TYPE_CHECKING:
    from ...messaging.whatsapp.models.basic_models import MessageResult
    from ...messaging.whatsapp.models.interactive_models import (
        InteractiveHeader,
        ListSection,
        ReplyButton,
    )

logger = logging.getLogger(__name__)


class PubSubMessengerWrapper(IMessenger):
    # Wraps IMessenger and publishes bot_reply notifications on send.
    # Channel: wappa:notify:{tenant}:{user_id}:bot_reply

    def __init__(
        self,
        inner: IMessenger,
        tenant: str,
        user_id: str,
    ):
        warnings.warn(
            "PubSubMessengerWrapper is deprecated; register "
            "PubSubNotificationMiddleware via WappaBuilder.add_messenger_middleware "
            "instead. This class will be removed in v0.6.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._inner = inner
        self._tenant = tenant
        self._user_id = user_id

    async def _publish_bot_reply(
        self,
        message_type: str,
        result: MessageResult,
    ) -> None:
        if not result.success:
            return

        await publish_notification(
            event_type="bot_reply",
            tenant=self._tenant,
            user_id=self._user_id,
            platform=self._inner.platform.value,
            data={
                "message_id": result.message_id or "",
                "message_type": message_type,
            },
        )

    async def _send_with_notification(
        self,
        message_type: str,
        operation: Awaitable[MessageResult],
    ) -> MessageResult:
        result = await operation
        await self._publish_bot_reply(message_type, result)
        return result

    # Properties - delegate to inner
    @property
    def platform(self) -> PlatformType:
        return self._inner.platform

    @property
    def tenant_id(self) -> str:
        return self._inner.tenant_id

    # Basic messaging
    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._send_with_notification(
            "text",
            self._inner.send_text(
                text,
                recipient,
                reply_to_message_id,
                disable_preview,
            ),
        )

    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult:
        # No notification for mark_as_read - it's not a message
        return await self._inner.mark_as_read(message_id, typing)

    # Media messaging
    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_notification(
            "image",
            self._inner.send_image(
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
        return await self._send_with_notification(
            "video",
            self._inner.send_video(
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
        return await self._send_with_notification(
            "audio",
            self._inner.send_audio(
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
        return await self._send_with_notification(
            "document",
            self._inner.send_document(
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
        return await self._send_with_notification(
            "sticker",
            self._inner.send_sticker(
                sticker_source,
                recipient,
                reply_to_message_id,
            ),
        )

    # Interactive messaging
    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        recipient: str,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._send_with_notification(
            "button",
            self._inner.send_button_message(
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
        return await self._send_with_notification(
            "list",
            self._inner.send_list_message(
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
        return await self._send_with_notification(
            "cta",
            self._inner.send_cta_message(
                button_text,
                button_url,
                recipient,
                body,
                header,
                footer,
                reply_to_message_id,
            ),
        )

    # Template messaging
    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        return await self._send_with_notification(
            "template",
            self._inner.send_text_template(
                template_name,
                recipient,
                body_parameters,
                language_code,
                template_type=template_type,
                override=override,
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
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        return await self._send_with_notification(
            "template",
            self._inner.send_media_template(
                template_name,
                recipient,
                media_type,
                media_id,
                media_url,
                body_parameters,
                language_code,
                template_type=template_type,
                override=override,
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
        *,
        template_type: str,
        override: bool | None = None,
    ) -> MessageResult:
        return await self._send_with_notification(
            "template",
            self._inner.send_location_template(
                template_name,
                recipient,
                latitude,
                longitude,
                name,
                address,
                body_parameters,
                language_code,
                template_type=template_type,
                override=override,
            ),
        )

    # Specialized messaging
    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        return await self._send_with_notification(
            "contact",
            self._inner.send_contact(contact, recipient, reply_to_message_id),
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
        return await self._send_with_notification(
            "location",
            self._inner.send_location(
                latitude,
                longitude,
                recipient,
                name,
                address,
                reply_to_message_id,
            ),
        )

    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        return await self._send_with_notification(
            "location_request",
            self._inner.send_location_request(
                body,
                recipient,
                reply_to_message_id,
            ),
        )
