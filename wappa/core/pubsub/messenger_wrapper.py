"""
Messenger wrapper that publishes PubSub notifications for bot-sent messages.

Wraps IMessenger to intercept all send_*() calls and publish bot_reply events.
This enables real-time notifications when bots send messages via process_message().
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.interfaces.messaging_interface import IMessenger
from ...schemas.core.types import PlatformType
from .handlers import publish_notification

if TYPE_CHECKING:
    from ...messaging.whatsapp.models.basic_models import MessageResult

logger = logging.getLogger(__name__)


class PubSubMessengerWrapper(IMessenger):
    """
    Wrapper that publishes bot_reply notifications for all messenger sends.

    Delegates all IMessenger methods to inner messenger while publishing
    PubSub notifications for successful sends. This enables frontends to
    receive real-time updates when bots send messages.

    Usage:
        # Automatically applied by RedisPubSubPlugin when publish_bot_replies=True
        # The wrapper is injected in webhook_controller.py

    Channel: wappa:notify:{tenant}:{user_id}:bot_reply
    """

    def __init__(
        self,
        inner: IMessenger,
        tenant: str,
        user_id: str,
    ):
        """
        Initialize wrapper.

        Args:
            inner: The actual messenger to delegate calls to
            tenant: Tenant identifier for notifications
            user_id: User ID for notifications (recipient of bot messages)
        """
        self._inner = inner
        self._tenant = tenant
        self._user_id = user_id

    async def _publish_bot_reply(
        self,
        message_type: str,
        result: MessageResult,
    ) -> None:
        """Publish bot_reply notification after successful send."""
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
        result = await self._inner.send_text(
            text, recipient, reply_to_message_id, disable_preview
        )
        await self._publish_bot_reply("text", result)
        return result

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
        result = await self._inner.send_image(
            image_source, recipient, caption, reply_to_message_id
        )
        await self._publish_bot_reply("image", result)
        return result

    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_video(
            video_source, recipient, caption, reply_to_message_id
        )
        await self._publish_bot_reply("video", result)
        return result

    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_audio(
            audio_source, recipient, reply_to_message_id
        )
        await self._publish_bot_reply("audio", result)
        return result

    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_document(
            document_source, recipient, filename, caption, reply_to_message_id
        )
        await self._publish_bot_reply("document", result)
        return result

    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_sticker(
            sticker_source, recipient, reply_to_message_id
        )
        await self._publish_bot_reply("sticker", result)
        return result

    # Interactive messaging
    async def send_button_message(
        self,
        buttons: list[dict[str, str]],
        recipient: str,
        body: str,
        header: dict | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_button_message(
            buttons, recipient, body, header, footer, reply_to_message_id
        )
        await self._publish_bot_reply("button", result)
        return result

    async def send_list_message(
        self,
        sections: list[dict],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_list_message(
            sections, recipient, body, button_text, header, footer, reply_to_message_id
        )
        await self._publish_bot_reply("list", result)
        return result

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
        result = await self._inner.send_cta_message(
            button_text,
            button_url,
            recipient,
            body,
            header,
            footer,
            reply_to_message_id,
        )
        await self._publish_bot_reply("cta", result)
        return result

    # Template messaging
    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        result = await self._inner.send_text_template(
            template_name, recipient, body_parameters, language_code
        )
        await self._publish_bot_reply("template", result)
        return result

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
        result = await self._inner.send_media_template(
            template_name,
            recipient,
            media_type,
            media_id,
            media_url,
            body_parameters,
            language_code,
        )
        await self._publish_bot_reply("template", result)
        return result

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
        result = await self._inner.send_location_template(
            template_name,
            recipient,
            latitude,
            longitude,
            name,
            address,
            body_parameters,
            language_code,
        )
        await self._publish_bot_reply("template", result)
        return result

    # Specialized messaging
    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        result = await self._inner.send_contact(contact, recipient, reply_to_message_id)
        await self._publish_bot_reply("contact", result)
        return result

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        result = await self._inner.send_location(
            latitude, longitude, recipient, name, address, reply_to_message_id
        )
        await self._publish_bot_reply("location", result)
        return result

    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult:
        result = await self._inner.send_location_request(
            body, recipient, reply_to_message_id
        )
        await self._publish_bot_reply("location_request", result)
        return result
