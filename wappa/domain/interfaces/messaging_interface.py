# Platform-agnostic messaging interface contract (WhatsApp/Telegram/Teams/...).

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

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
        InteractiveHeader,
        ListSection,
        MessageCard,
        ReplyButton,
    )
    from wappa.domain.interfaces.media_library import IMediaLibrary
    from wappa.domain.results import MessageResult
    from wappa.domain.user_profile import PlatformUserProfile
    from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

TemplateBodyParameters = list[dict] | None
TemplateRoutingPolicyValue = str
# ``one_tap`` | ``zero_tap`` | ``copy_code`` when the Template is an
# Authentication Template, ``None`` for every other category. Kept a primitive
# so the platform-agnostic contract stays free of WhatsApp enums.
TemplateAuthenticationMethodValue = str | None


class IMessenger(ABC):
    """Inbox-bound facade: one method per action on every Platform (ADR-0025).

    Each Platform adapter maps these methods onto its native API. Operations a
    Platform lacks raise ``UnsupportedOperationError``; check
    ``supported_operations`` instead of branching on the Platform name.
    A capability every Platform provides is a ready attribute: ``media``
    (``IMediaLibrary``). Platform-only actions are ready on that Platform's
    Platform Messenger (``self.whatsapp.templates``,
    ``self.instagram.comments`` on the handler). ``capability()`` is the
    internal seam both are built on (adapters, ``MessengerPipeline``, HTTP
    ``requires_capability``); Host code does not call it.

    ``transcript`` (``send_video`` / ``send_audio``) is middleware-only
    metadata: no adapter sends it to the Platform, and middleware reads it
    from the ``SendInvocation`` arguments (e.g. to store what an AI Agent
    said in a voice note).
    """

    # Platform-only capabilities by interface, filled once in each adapter's
    # constructor. The one lookup below reads it; adapters never override it.
    _capabilities: Mapping[type, object] = MappingProxyType({})

    @property
    def supported_operations(self) -> frozenset[str]:
        """Implemented adapter operations, not the provider's full feature catalog."""
        return frozenset({"send_text", "resolve_platform_user_profile"})

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        """Return a focused optional capability by its interface (e.g. ``ICommentControls``).

        ``None`` means this Platform adapter does not implement it. Capabilities
        are bound to this Messenger's Inbox and credentials and are looked up
        by the interface only, never by a concrete adapter class.
        """
        return cast("C | None", self._capabilities.get(cast(type, kind)))

    def require_capability[C](self, kind: Callable[..., C]) -> C:
        found = self.capability(kind)
        if found is None:
            raise UnsupportedOperationError(
                f"{self.platform.value} does not provide {getattr(kind, '__name__', kind)}"
            )
        return found

    @property
    def media(self) -> IMediaLibrary:
        """This Inbox's Media Library (ADR-0025 rule 9), ready on every Platform.

        Upload, download, describe and delete Platform media. Raises
        ``UnsupportedOperationError`` only on an adapter that provides none.
        """
        from wappa.domain.interfaces.media_library import IMediaLibrary

        return self.require_capability(IMediaLibrary)

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

    @abstractmethod
    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        """Every fact this Platform provides about ``user`` (ADR-0025 rule 10).

        Read-only and never called by Wappa during intake or dispatch; the
        Host merges, persists and re-resolves. WhatsApp maps the webhook
        evidence with no I/O. Instagram adds a Graph profile lookup with the
        Inbox token and, when it fails, returns the evidence with the failure
        ``outcome`` instead of raising. ``user`` must be this Platform's
        evidence (``ValueError`` otherwise).
        """

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
        """Send a video. ``transcript`` is middleware-only metadata, never sent."""
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
        note on both Platforms from the same call. ``transcript`` is
        middleware-only metadata: no Platform receives it.
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
        header: InteractiveHeader | None = None,
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
        header: str | None = None,
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
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """One URL button. ``header`` is text or media, as on WhatsApp.

        Limits (``check_cta_message``) are the shared minimum across
        Platforms. Instagram folds a text header and footer into the button
        text and sends a media header first as its own message.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_cta_message"
        )

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """A horizontally scrollable carousel of 2–10 cards with an intro ``body``.

        Card rules are checked when the value is built (``MessageCard``:
        a ``header`` image or video by public URL, one URL button or reply
        buttons) and by ``check_carousel`` (2–10 cards, the same button kind
        and count on every card). WhatsApp: interactive media carousel.
        Instagram: ``body`` as a text message (carrying the reply context),
        then a generic template; a video card needs ``header.poster_url``. A
        single card is ``send_button_message`` with a media header.
        """
        raise UnsupportedOperationError(
            f"{self.platform.value} does not support send_carousel"
        )

    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Send one contact card or several in one message.

        WhatsApp: one native contacts message. Instagram: each card as a text
        block, split over several messages beyond 1000 UTF-8 bytes.
        """
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
