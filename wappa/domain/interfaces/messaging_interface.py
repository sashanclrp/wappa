# Platform-agnostic messaging interface contract (WhatsApp/Telegram/Teams/...).

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from wappa.domain.contacts import ContactCard
from wappa.domain.media_renditions import MediaRenditions
from wappa.domain.messaging_targets import (
    DirectMessage,
    MessageTarget,
    UnsupportedOperationError,
)
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.domain.interactive import (
        ButtonHeader,
        ListSection,
        MessageCard,
        ReplyButton,
    )
    from wappa.domain.results import MessageResult

TemplateBodyParameters = list[dict] | None
TemplateRoutingPolicyValue = str
# ``one_tap`` | ``zero_tap`` | ``copy_code`` when the Template is an
# Authentication Template, ``None`` for every other category. Kept a primitive
# so the platform-agnostic contract stays free of WhatsApp enums.
TemplateAuthenticationMethodValue = str | None


class IMessenger(ABC):
    """Inbox-bound facade: one method per action on every Platform (ADR-0016).

    Each Platform adapter maps these methods onto its native API. Operations a
    Platform lacks raise ``UnsupportedOperationError``; check
    ``supported_operations`` instead of branching on the Platform name.
    Platform-only actions live behind ``capability()``: e.g. WhatsApp
    Templates (``ITemplateMessaging``) and Instagram comments
    (``ICommentControls``).
    """

    @property
    def supported_operations(self) -> frozenset[str]:
        """Implemented adapter operations, not the provider's full feature catalog."""
        return frozenset({"send_text"})

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        """Return a focused optional capability (e.g. ``ICommentControls``).

        ``None`` means this Platform adapter does not implement it. Capabilities
        are bound to this Messenger's Inbox and credentials.
        """
        _ = kind
        return None

    def require_capability[C](self, kind: Callable[..., C]) -> C:
        found = self.capability(kind)
        if found is None:
            raise UnsupportedOperationError(
                f"{self.platform.value} does not provide {getattr(kind, '__name__', kind)}"
            )
        return found

    @property
    @abstractmethod
    def platform(self) -> PlatformType: ...

    @property
    @abstractmethod
    def inbox_id(self) -> str: ...

    @abstractmethod
    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        """Send text to a DirectMessage, or a PrivateReply where supported.

        Adapters without private replies reject ``PrivateReply`` explicitly.
        """

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        """Acknowledge the User's inbound message, optionally showing typing.

        One call for every Platform. WhatsApp marks ``message_id`` read and,
        with ``typing``, shows the indicator until the reply (or ~25 s).
        Instagram has no per-message read: it marks the thread seen named by
        ``target``, then ``typing_on``. WhatsApp only checks ``target``
        against its Inbox.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support mark_as_read"
        )

    # Media
    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_image"
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_video"
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        """Send audio. ``is_voice=True`` asks for a voice note (waveform).

        ``audio_source`` is one source or a list of renditions of the same
        audio; each adapter sends the first one its Platform accepts
        (Wappa never converts):

        - WhatsApp voice note (``is_voice=True``): ``.ogg`` (Opus, mono) only.
        - WhatsApp audio: ``.aac``, ``.amr``, ``.mp3``, ``.m4a`` or ``.ogg`` (16 MB).
        - Instagram: ``.aac``, ``.m4a``, ``.wav`` or ``.mp4`` (25 MB). Instagram
          shows every audio attachment as a voice message, so ``is_voice`` has
          no effect there.

        A single source without an extension (a Platform media ID) is passed
        through. ``ValueError`` before any Platform call when no rendition fits.
        Pass ``["note.ogg", "note.m4a"]`` with ``is_voice=True`` to send a voice
        note on both Platforms from the same call.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_audio"
        )

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_document"
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send a sticker. Formats differ per Platform; Wappa never converts.

        ``sticker_source`` is one source or a list of renditions of the same
        sticker. Each adapter sends the first rendition its Platform accepts:

        - WhatsApp: ``.webp`` only (512x512; 100 KB static, 500 KB animated).
        - Instagram: no stickers; sent as an image, so ``.png``, ``.jpg``,
          ``.jpeg`` or ``.gif`` (8 MB).

        A single source without an extension (a Platform media ID) is passed
        through. ``ValueError`` before any Platform call when no rendition fits.
        Pass ``["sticker.webp", "sticker.png"]`` to serve both Platforms.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_sticker"
        )

    # Interactive
    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_button_message"
        )

    async def send_list_message(
        self,
        sections: list[ListSection],
        target: DirectMessage,
        body: str,
        button_text: str,
        header: ButtonHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_list_message"
        )

    async def send_cta_message(
        self,
        button_text: str,
        button_url: str,
        target: DirectMessage,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_cta_message"
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
    ) -> MessageResult:
        """A horizontally scrollable carousel of 2–10 cards with an intro ``body``.

        WhatsApp: interactive media carousel (every card needs ``image_url``;
        buttons must match across cards). Instagram: ``body`` as a text message,
        then a generic template. A single card is ``send_button_message`` with an
        image header.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_carousel"
        )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_contact_request"
        )

    async def send_contact(
        self,
        contact: ContactCard,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_contact"
        )

    async def send_location(
        self,
        latitude: float,
        longitude: float,
        target: DirectMessage,
        name: str | None = None,
        address: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_location"
        )

    async def send_location_request(
        self, body: str, target: DirectMessage, reply_to_message_id: str | None = None
    ) -> MessageResult:
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_location_request"
        )
