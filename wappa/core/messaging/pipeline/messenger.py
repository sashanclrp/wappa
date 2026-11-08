"""``MessengerPipeline``: the ``IMessenger`` composed from a raw messenger and middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from wappa.domain.messenger_discovery import MessengerDiscovery

from ....domain.contacts import ContactCard
from ....domain.inbox.identity import InboxRef
from ....domain.interfaces.messaging_interface import IMessenger
from ....domain.interfaces.template_messaging import (
    TEMPLATE_METHODS,
    ITemplateMessaging,
)
from ....domain.interfaces.user_data_requests import (
    USER_DATA_REQUEST_METHODS,
    IUserDataRequests,
)
from ....domain.media_renditions import MediaRenditions
from ....domain.messaging_targets import DirectMessage, MessageTarget
from ....schemas.core.types import PlatformType
from .capabilities import _PipelineTemplates, _PipelineUserDataRequests
from .invocation import (
    MessengerMiddleware,
    MiddlewareEntry,
    SendInvocation,
    SendNext,
    _bind,
)

if TYPE_CHECKING:
    from wappa.domain.interactive import InteractiveHeader, ListSection, ReplyButton
    from wappa.domain.results import MessageResult
    from wappa.domain.user_profile import PlatformUserProfile
    from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

    from ....domain.interactive import MessageCard


class MessengerPipeline(IMessenger):
    """``IMessenger`` implementation composed from raw messenger + middleware.

    The ``IMessenger`` methods are implemented here exactly once. Each
    builds a :class:`SendInvocation` and hands it to :meth:`_dispatch`,
    which walks the chain from outer to inner middleware and finally
    invokes the matching method on the raw messenger via reflection.
    """

    def __init__(
        self,
        raw: IMessenger,
        middleware: Sequence[MiddlewareEntry] = (),
    ) -> None:
        self._raw = raw
        # Sort descending: higher priority = outer = runs first.
        self._middleware: tuple[MessengerMiddleware, ...] = tuple(
            mw for mw, _ in sorted(middleware, key=lambda entry: entry[1], reverse=True)
        )
        # Pre-compose the dispatch chain once. Middleware is app-scoped and
        # immutable after construction, so the bound chain is safe to reuse
        # across every outbound call — no need to rebuild per dispatch.
        self._entrypoint: SendNext = self._call_raw
        for mw in reversed(self._middleware):
            self._entrypoint = _bind(mw, self._entrypoint)

    # ------------------------------------------------------------------ #
    # Introspection (public — replaces the need to access private `_inner`).
    # ------------------------------------------------------------------ #

    @property
    def raw_messenger(self) -> IMessenger:
        """The underlying transport messenger, without any middleware."""
        return self._raw

    @property
    def middleware_chain(self) -> tuple[MessengerMiddleware, ...]:
        """Registered middleware, ordered outer → inner."""
        return self._middleware

    # ------------------------------------------------------------------ #
    # IMessenger identity props — delegated to raw.
    # ------------------------------------------------------------------ #

    @property
    def discovery(self) -> MessengerDiscovery:
        """Supported suboperations, receipt semantics, target kinds and limits."""
        return self._raw.discovery

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._raw.supported_operations

    @property
    def platform(self) -> PlatformType:
        return self._raw.platform

    @property
    def inbox_id(self) -> str:
        return self._raw.inbox_id

    # ------------------------------------------------------------------ #
    # Dispatch core.
    # ------------------------------------------------------------------ #

    async def _call_raw(self, invocation: SendInvocation) -> MessageResult:
        owner: object = self._raw
        if invocation.method_name in TEMPLATE_METHODS:
            owner = self._raw.require_capability(ITemplateMessaging)
        elif invocation.method_name in USER_DATA_REQUEST_METHODS:
            owner = self._raw.require_capability(IUserDataRequests)
        method = getattr(owner, invocation.method_name)
        result: MessageResult = await method(*invocation.args, **invocation.kwargs)
        return result

    def _invoke(
        self,
        method_name: str,
        message_type: str,
        target: MessageTarget,
        arguments: Mapping[str, Any],
        *,
        keyword_only: Mapping[str, Any] | None = None,
    ) -> Awaitable[MessageResult]:
        """Build the :class:`SendInvocation` and hand it to the pre-composed chain.

        ``args`` is derived from ``arguments.values()``; each ``send_*``
        method defines ``arguments`` in positional order so the tuple matches
        what the raw messenger expects.

        ``keyword_only``, when provided, names arguments that must be passed
        as **kwargs** to the raw messenger (keyword-only parameters after
        ``*``). Those keys are excluded from the positional ``args`` tuple
        but remain in ``arguments`` for middleware inspection.
        """
        target.resolve(InboxRef(platform=self.platform, inbox_id=self.inbox_id))
        kw = keyword_only or {}
        positional = {k: v for k, v in arguments.items() if k not in kw}
        return self._entrypoint(
            SendInvocation(
                method_name=method_name,
                message_type=message_type,
                target=target,
                args=tuple(positional.values()),
                kwargs=kw,
                arguments=arguments,
            )
        )

    # ------------------------------------------------------------------ #
    # IMessenger basic messaging.
    # ------------------------------------------------------------------ #

    def capability[C](self, kind: Callable[..., C]) -> C | None:
        # Template sends and user-data requests are messages: wrap them so
        # middleware still runs. Every other focused capability bypasses it.
        found = self._raw.capability(kind)
        if kind is ITemplateMessaging and found is not None:
            return _PipelineTemplates(self)  # type: ignore[return-value]
        if kind is IUserDataRequests and found is not None:
            return _PipelineUserDataRequests(self)  # type: ignore[return-value]
        return found

    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._invoke(
            "send_text",
            "text",
            target,
            {
                "text": text,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
                "disable_preview": disable_preview,
            },
        )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        # mark_as_read isn't really an outbound message — skip the pipeline
        # to preserve semantics (no wrapper ever published it anyway).
        return await self._raw.mark_as_read(message_id, target, typing=typing)

    async def resolve_platform_user_profile(
        self, user: UserBase
    ) -> PlatformUserProfile:
        # A read, not an outbound message: no SendInvocation, no middleware.
        return await self._raw.resolve_platform_user_profile(user)

    async def send_carousel(
        self,
        cards: Sequence[MessageCard],
        target: DirectMessage,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_carousel",
            "interactive",
            target,
            {
                "cards": cards,
                "target": target,
                "body": body,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger media.
    # ------------------------------------------------------------------ #

    async def send_image(
        self,
        image_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_image",
            "image",
            target,
            {
                "image_source": image_source,
                "target": target,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_video(
        self,
        video_source: str | Path,
        target: DirectMessage,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_video",
            "video",
            target,
            {
                "video_source": video_source,
                "target": target,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
            },
        )

    async def send_audio(
        self,
        audio_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
        is_voice: bool = False,
    ) -> MessageResult:
        return await self._invoke(
            "send_audio",
            "audio",
            target,
            {
                "audio_source": audio_source,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
                "is_voice": is_voice,
            },
        )

    async def send_document(
        self,
        document_source: str | Path,
        target: DirectMessage,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_document",
            "document",
            target,
            {
                "document_source": document_source,
                "target": target,
                "filename": filename,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_sticker(
        self,
        sticker_source: MediaRenditions,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_sticker",
            "sticker",
            target,
            {
                "sticker_source": sticker_source,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger interactive.
    # ------------------------------------------------------------------ #

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        target: DirectMessage,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_button_message",
            "button",
            target,
            {
                "buttons": buttons,
                "target": target,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
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
        return await self._invoke(
            "send_list_message",
            "list",
            target,
            {
                "sections": sections,
                "target": target,
                "body": body,
                "button_text": button_text,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
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
        return await self._invoke(
            "send_cta_message",
            "cta",
            target,
            {
                "button_text": button_text,
                "button_url": button_url,
                "target": target,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger specialized.
    # ------------------------------------------------------------------ #

    async def send_contact(
        self,
        contacts: ContactCard | Sequence[ContactCard],
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_contact",
            "contact",
            target,
            {
                "contacts": contacts,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
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
        return await self._invoke(
            "send_location",
            "location",
            target,
            {
                "latitude": latitude,
                "longitude": longitude,
                "target": target,
                "name": name,
                "address": address,
                "reply_to_message_id": reply_to_message_id,
            },
        )
