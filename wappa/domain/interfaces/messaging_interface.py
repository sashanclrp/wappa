# Platform-agnostic messaging interface contract (WhatsApp/Telegram/Teams/...).

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.messaging.whatsapp.models.basic_models import MessageResult
    from wappa.messaging.whatsapp.models.interactive_models import (
        InteractiveHeader,
        ListSection,
        ReplyButton,
    )


class IMessenger(ABC):
    @property
    @abstractmethod
    def platform(self) -> PlatformType: ...

    @property
    @abstractmethod
    def tenant_id(self) -> str: ...

    @abstractmethod
    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult: ...

    @abstractmethod
    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult: ...

    # Media
    @abstractmethod
    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    # Interactive
    @abstractmethod
    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        recipient: str,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_list_message(
        self,
        sections: list[ListSection],
        recipient: str,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    # Templates
    @abstractmethod
    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult: ...

    @abstractmethod
    async def send_media_template(
        self,
        template_name: str,
        recipient: str,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult: ...

    @abstractmethod
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
    ) -> MessageResult: ...

    # Specialized
    @abstractmethod
    async def send_contact(
        self, contact: dict, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult: ...

    @abstractmethod
    async def send_location(
        self,
        latitude: float,
        longitude: float,
        recipient: str,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult: ...

    @abstractmethod
    async def send_location_request(
        self, body: str, recipient: str, reply_to_message_id: str | None = None
    ) -> MessageResult: ...
