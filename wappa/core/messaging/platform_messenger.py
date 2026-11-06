"""The Platform Messenger base: the dispatch's Messenger plus one Platform's extras.

A Platform Messenger (``self.whatsapp``, ``self.instagram`` on the handler)
receives the core Messenger the runtime already built for the dispatch, the
``MessengerPipeline``-wrapped one, and adds only its Platform's ready
capabilities. Every ``IMessenger`` member forwards to that Messenger, so
middleware runs exactly as it does for ``self.messenger``; capability lookups
forward too, so message capabilities (Templates, user-data requests) keep the
pipeline wrapping.

Each Platform's subclass lives in its adapter folder and is built by its
``PlatformEntry.build_platform_messenger`` in ``wappa/platforms.py``
(ADR-0025 rule 12).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from wappa.domain.contacts import ContactCard
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.media_renditions import MediaRenditions
from wappa.domain.messaging_targets import DirectMessage, MessageTarget
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.domain.interactive import (
        InteractiveHeader,
        ListSection,
        MessageCard,
        ReplyButton,
    )
    from wappa.domain.results import MessageResult
    from wappa.domain.user_profile import PlatformUserProfile
    from wappa.webhooks.core.webhook_interfaces.base_components import UserBase


class PlatformMessenger(IMessenger):
    """Forward the whole ``IMessenger`` contract to the dispatch's Messenger."""

    def __init__(self, messenger: IMessenger) -> None:
        self._messenger = messenger

    @property
    def messenger(self) -> IMessenger:
        """The core Messenger this Platform Messenger extends."""
        return self._messenger

    # ── identity and capability lookup ──────────────────────────────────

    @property
    def platform(self) -> PlatformType:
        return self._messenger.platform

    @property
    def inbox_id(self) -> str:
        return self._messenger.inbox_id

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._messenger.supported_operations

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        return self._messenger.capability(kind)

    # ── the core contract, forwarded ────────────────────────────────────

    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._messenger.send_text(
            text, target, reply_to_message_id, disable_preview
        )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        return await self._messenger.mark_as_read(message_id, target, typing=typing)

    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        return await self._messenger.resolve_platform_user_profile(user)

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_image(
            image_source, target, caption, reply_to_message_id
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_video(
            video_source, target, caption, reply_to_message_id, transcript
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        return await self._messenger.send_audio(
            audio_source, target, reply_to_message_id, transcript, is_voice
        )

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_document(
            document_source, target, filename, caption, reply_to_message_id
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_sticker(
            sticker_source, target, reply_to_message_id
        )

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_button_message(
            buttons, target, body, header, footer, reply_to_message_id
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        target: DirectMessage,
        body: str,
        button_text: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_list_message(
            sections, target, body, button_text, header, footer, reply_to_message_id
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_cta_message(
            button_text, button_url, target, body, header, footer, reply_to_message_id
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_carousel(
            cards, target, body, reply_to_message_id
        )

    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_contact(contacts, target, reply_to_message_id)

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._messenger.send_location(
            latitude, longitude, target, name, address, reply_to_message_id
        )


__all__ = ["PlatformMessenger"]
