"""Credential-independent Messenger for scheduled scopes."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from wappa.domain.contacts import ContactCard
from wappa.domain.inbox.identity import InboxRef
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


class DeferredMessenger(IMessenger):
    """Resolve one scope's pipeline on first operation, never on binding.

    Only successful construction is retained. A lock serializes concurrent first
    operations while allowing the next operation to retry a failed resolution.
    Discovery comes from the Platform entry and needs no credentials.
    """

    def __init__(
        self,
        inbox_ref: InboxRef,
        resolve: Callable[[], Awaitable[IMessenger]],
        *,
        supported_operations: frozenset[str],
        capability_types: frozenset[type],
    ) -> None:
        self._inbox_ref = inbox_ref
        self._resolve = resolve
        self._resolved: IMessenger | None = None
        self._lock = asyncio.Lock()
        self._operations = supported_operations
        self._capability_types = capability_types

    async def _get(self) -> IMessenger:
        if self._resolved is None:
            async with self._lock:
                if self._resolved is None:
                    self._resolved = await self._resolve()
        return self._resolved

    @property
    def platform(self) -> PlatformType:
        return self._inbox_ref.platform

    @property
    def inbox_id(self) -> str:
        return self._inbox_ref.inbox_id

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._operations

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        if self._resolved is not None:
            return self._resolved.capability(kind)
        if kind not in self._capability_types:
            return None
        return cast(C, _DeferredCapability(self._get, kind))

    # ── the core contract, forwarded ────────────────────────────────────

    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_text(
            text, target, reply_to_message_id, disable_preview
        )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.mark_as_read(message_id, target, typing=typing)

    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        messenger = await self._get()
        return await messenger.resolve_platform_user_profile(user)

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_image(
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
        messenger = await self._get()
        return await messenger.send_video(
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
        messenger = await self._get()
        return await messenger.send_audio(
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
        messenger = await self._get()
        return await messenger.send_document(
            document_source, target, filename, caption, reply_to_message_id
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_sticker(sticker_source, target, reply_to_message_id)

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_button_message(
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
        messenger = await self._get()
        return await messenger.send_list_message(
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
        messenger = await self._get()
        return await messenger.send_cta_message(
            button_text, button_url, target, body, header, footer, reply_to_message_id
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_carousel(cards, target, body, reply_to_message_id)

    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_contact(contacts, target, reply_to_message_id)

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        messenger = await self._get()
        return await messenger.send_location(
            latitude, longitude, target, name, address, reply_to_message_id
        )


class _DeferredCapability:
    """Delay a focused capability's async calls through the same pipeline.

    Focused capabilities expose async operations; discovery itself performs no
    I/O. The resolved capability remains responsible for its actual method set.
    """

    def __init__(
        self,
        messenger: Callable[[], Awaitable[IMessenger]],
        kind: Callable[..., Any],
    ) -> None:
        self._messenger = messenger
        self._kind = kind

    def __getattr__(self, name: str) -> Any:
        async def call(*args: Any, **kwargs: Any) -> Any:
            messenger = await self._messenger()
            capability = messenger.require_capability(self._kind)
            return await getattr(capability, name)(*args, **kwargs)

        return call
