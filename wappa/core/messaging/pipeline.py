"""Messenger middleware pipeline.

A :class:`MessengerPipeline` implements :class:`IMessenger` once. Every
outbound call is captured into a :class:`SendInvocation` and dispatched
through a priority-ordered chain of :class:`MessengerMiddleware` instances,
ASGI-style. Higher priority = closer to the caller (outer); lower priority
= closer to the raw transport (inner).

Priority convention (docs, not enforced):

    10  reliability         (retry, circuit-breaker)
    30  domain notifications (pub/sub)
    50  caching / persistence
    70  lifecycle events     (SSE)
    90  observability        (metrics, tracing)

Example::

    pipeline = MessengerPipeline(
        raw=whatsapp_messenger,
        middleware=[(cache_mw, 50), (sse_mw, 70)],
    )
    await pipeline.send_text("hi", target)
    # Flow: caller → sse_mw(70) → cache_mw(50) → raw.send_text

Adding a new :class:`IMessenger` method requires a one-method addition here;
middleware code stays untouched.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from ...domain.contacts import ContactCard
from ...domain.inbox.identity import InboxRef
from ...domain.interfaces.messaging_interface import IMessenger
from ...domain.interfaces.template_messaging import (
    TEMPLATE_METHODS,
    ITemplateMessaging,
)
from ...domain.interfaces.user_data_requests import (
    USER_DATA_REQUEST_METHODS,
    IUserDataRequests,
)
from ...domain.media_renditions import MediaRenditions
from ...domain.messaging_targets import DirectMessage, MessageTarget
from ...schemas.core.types import PlatformType

if TYPE_CHECKING:
    from wappa.domain.interactive import InteractiveHeader, ListSection, ReplyButton
    from wappa.domain.results import MessageResult
    from wappa.domain.user_profile import PlatformUserProfile
    from wappa.webhooks.core.webhook_interfaces.base_components import UserBase

    from ...domain.interactive import MessageCard


# Canonical priority bands. Middleware registers with a numeric priority;
# these names exist only for documentation and tests.
PRIORITY_RELIABILITY: int = 10
PRIORITY_NOTIFICATIONS: int = 30
PRIORITY_CACHE: int = 50
PRIORITY_LIFECYCLE: int = 70
PRIORITY_OBSERVABILITY: int = 90


@dataclass(frozen=True, slots=True)
class SendInvocation:
    """Structured view of one outbound call travelling through the pipeline.

    Middleware reads ``method_name``, ``message_type``, ``target`` for
    routing decisions and ``arguments`` for the named payload. The
    invocation is immutable; middleware that needs to rewrite arguments
    constructs a new invocation via :meth:`with_arguments` before calling
    ``call_next``.

    - ``args``/``kwargs`` are what the raw messenger method receives
      (positional + keyword). The pipeline calls
      ``getattr(raw, method_name)(*args, **kwargs)``.
    - ``arguments`` is the same information keyed by parameter name, used
      for event emission and logging. It is canonical for middleware that
      serialize or inspect payloads.
    """

    method_name: str
    message_type: str
    target: MessageTarget
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    arguments: Mapping[str, Any] = field(default_factory=dict)

    @property
    def recipient(self) -> str:
        """Native address evidence for middleware; sending uses target.

        A DirectMessage yields its recipient ID; a PrivateReply yields
        ``comment:<comment_id>`` because the User is not yet addressable.
        """
        return self.target.address

    def with_arguments(
        self,
        arguments: Mapping[str, Any],
        *,
        args: tuple[Any, ...] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> SendInvocation:
        """Return a copy with substituted arguments (for middleware rewrites).

        If ``args``/``kwargs`` are not supplied, they default to the values
        in ``arguments`` (in insertion order for ``args``). Callers that
        need a different positional shape pass both explicitly.
        """
        resolved_args = args if args is not None else tuple(arguments.values())
        resolved_kwargs = kwargs if kwargs is not None else {}
        return SendInvocation(
            method_name=self.method_name,
            message_type=self.message_type,
            target=self.target,
            args=resolved_args,
            kwargs=resolved_kwargs,
            arguments=arguments,
        )

    def to_request_payload(self) -> dict[str, Any]:
        """Serializable named-argument payload (for event emission)."""
        return cast(dict[str, Any], _to_serializable(dict(self.arguments)))


SendNext = Callable[[SendInvocation], Awaitable["MessageResult"]]


@runtime_checkable
class MessengerMiddleware(Protocol):
    """Cross-cutting concern around an outbound :class:`IMessenger` call.

    Implementations receive the captured :class:`SendInvocation` plus a
    ``call_next`` callable. They may do work before and/or after awaiting
    ``call_next``, short-circuit by returning without calling it, or
    rewrite the invocation and forward it.

    Middleware is app-scoped (constructed once at ``WappaBuilder.build``);
    per-request identity comes from ContextVars (see
    ``wappa.core.sse.context.SSEEventContext``).
    """

    name: str

    async def handle(
        self,
        invocation: SendInvocation,
        call_next: SendNext,
    ) -> MessageResult: ...


# (middleware, priority) — priority is stored alongside the middleware so
# the builder owns ordering, not the middleware itself.
MiddlewareEntry = tuple[MessengerMiddleware, int]


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


def _bind(mw: MessengerMiddleware, call_next: SendNext) -> SendNext:
    """Bind a middleware to the inner `call_next`, producing a new `call_next`."""

    async def invoke(invocation: SendInvocation) -> MessageResult:
        return await mw.handle(invocation, call_next)

    return invoke


def _to_serializable(value: Any) -> Any:
    """Coerce arbitrary values (Path, Pydantic models, containers) to JSON-safe."""
    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=False)

    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set):
        return [_to_serializable(item) for item in value]

    return value


class _PipelineTemplates(ITemplateMessaging):
    """Template capability that still runs the pipeline's message middleware.

    Invocations keep the historic method names (``send_text_template`` …) so
    window guards and cache middleware see Templates exactly as before.
    """

    def __init__(self, pipeline: MessengerPipeline) -> None:
        self._pipeline = pipeline

    async def send_text_template(
        self,
        template_name: str,
        target: DirectMessage,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
        authentication_method: str | None = None,
        authentication_button_index: int = 0,
    ) -> MessageResult:
        kw = {
            "template_type": template_type,
            "routing_policy": routing_policy,
            "authentication_method": authentication_method,
            "authentication_button_index": authentication_button_index,
        }
        return await self._pipeline._invoke(
            "send_text_template",
            "text_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
        )

    async def send_media_template(
        self,
        template_name: str,
        target: DirectMessage,
        media_type: str,
        media_id: str | None = None,
        media_url: str | None = None,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        kw = {"template_type": template_type, "routing_policy": routing_policy}
        return await self._pipeline._invoke(
            "send_media_template",
            "media_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "media_type": media_type,
                "media_id": media_id,
                "media_url": media_url,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
        )

    async def send_location_template(
        self,
        template_name: str,
        target: DirectMessage,
        latitude: str,
        longitude: str,
        name: str,
        address: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
        *,
        template_type: str,
        routing_policy: str = "category_default",
    ) -> MessageResult:
        kw = {"template_type": template_type, "routing_policy": routing_policy}
        return await self._pipeline._invoke(
            "send_location_template",
            "location_template",
            target,
            {
                "template_name": template_name,
                "target": target,
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
                "body_parameters": body_parameters,
                "language_code": language_code,
                **kw,
            },
            keyword_only=kw,
        )


class _PipelineUserDataRequests(IUserDataRequests):
    """User-data request capability that still runs the message middleware."""

    def __init__(self, pipeline: MessengerPipeline) -> None:
        self._pipeline = pipeline

    async def send_location_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._pipeline._invoke(
            "send_location_request",
            "location_request",
            target,
            {
                "body": body,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._pipeline._invoke(
            "send_contact_request",
            "request_contact_info",
            target,
            {
                "body": body,
                "target": target,
                "reply_to_message_id": reply_to_message_id,
            },
        )
