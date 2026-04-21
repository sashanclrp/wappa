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
    await pipeline.send_text("hi", recipient)
    # Flow: caller → sse_mw(70) → cache_mw(50) → raw.send_text

Adding a new :class:`IMessenger` method requires a one-method addition here;
middleware code stays untouched.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ...domain.interfaces.messaging_interface import IMessenger
from ...schemas.core.types import PlatformType

if TYPE_CHECKING:
    from ...messaging.whatsapp.models.basic_models import MessageResult
    from ...messaging.whatsapp.models.interactive_models import (
        InteractiveHeader,
        ListSection,
        ReplyButton,
    )


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

    Middleware reads ``method_name``, ``message_type``, ``recipient`` for
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
    recipient: str
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    arguments: Mapping[str, Any] = field(default_factory=dict)

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
            recipient=self.recipient,
            args=resolved_args,
            kwargs=resolved_kwargs,
            arguments=arguments,
        )

    def to_request_payload(self) -> dict[str, Any]:
        """Serializable named-argument payload (for event emission).

        Matches the legacy ``SSEMessengerWrapper`` ``request`` payload
        shape so existing SSE subscribers remain wire-compatible.
        """
        return _to_serializable(dict(self.arguments))


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

    The 18 ``IMessenger`` methods are implemented here exactly once. Each
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
    def platform(self) -> PlatformType:
        return self._raw.platform

    @property
    def tenant_id(self) -> str:
        return self._raw.tenant_id

    # ------------------------------------------------------------------ #
    # Dispatch core.
    # ------------------------------------------------------------------ #

    async def _call_raw(self, invocation: SendInvocation) -> MessageResult:
        method = getattr(self._raw, invocation.method_name)
        return await method(*invocation.args, **invocation.kwargs)

    def _invoke(
        self,
        method_name: str,
        message_type: str,
        recipient: str,
        arguments: dict[str, Any],
    ) -> Awaitable[MessageResult]:
        """Build the :class:`SendInvocation` and hand it to the pre-composed chain.

        ``args`` is derived from ``arguments.values()``; each ``send_*``
        method defines ``arguments`` in positional order so the tuple matches
        what the raw messenger expects. This keeps the 15 wrapper methods to
        a single line of dispatch each while preserving static signatures.
        """
        return self._entrypoint(
            SendInvocation(
                method_name=method_name,
                message_type=message_type,
                recipient=recipient,
                args=tuple(arguments.values()),
                arguments=arguments,
            )
        )

    # ------------------------------------------------------------------ #
    # IMessenger basic messaging.
    # ------------------------------------------------------------------ #

    async def send_text(
        self,
        text: str,
        recipient: str,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        return await self._invoke(
            "send_text",
            "text",
            recipient,
            {
                "text": text,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
                "disable_preview": disable_preview,
            },
        )

    async def mark_as_read(
        self, message_id: str, typing: bool = False
    ) -> MessageResult:
        # mark_as_read isn't really an outbound message — skip the pipeline
        # to preserve semantics (no wrapper ever published it anyway).
        return await self._raw.mark_as_read(message_id, typing)

    # ------------------------------------------------------------------ #
    # IMessenger media.
    # ------------------------------------------------------------------ #

    async def send_image(
        self,
        image_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_image",
            "image",
            recipient,
            {
                "image_source": image_source,
                "recipient": recipient,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_video(
        self,
        video_source: str | Path,
        recipient: str,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_video",
            "video",
            recipient,
            {
                "video_source": video_source,
                "recipient": recipient,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
            },
        )

    async def send_audio(
        self,
        audio_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
        transcript: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_audio",
            "audio",
            recipient,
            {
                "audio_source": audio_source,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
                "transcript": transcript,
            },
        )

    async def send_document(
        self,
        document_source: str | Path,
        recipient: str,
        filename: str | None = None,
        caption: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_document",
            "document",
            recipient,
            {
                "document_source": document_source,
                "recipient": recipient,
                "filename": filename,
                "caption": caption,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_sticker(
        self,
        sticker_source: str | Path,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_sticker",
            "sticker",
            recipient,
            {
                "sticker_source": sticker_source,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger interactive.
    # ------------------------------------------------------------------ #

    async def send_button_message(
        self,
        buttons: list[ReplyButton],
        recipient: str,
        body: str,
        header: InteractiveHeader | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_button_message",
            "button",
            recipient,
            {
                "buttons": buttons,
                "recipient": recipient,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
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
        return await self._invoke(
            "send_list_message",
            "list",
            recipient,
            {
                "sections": sections,
                "recipient": recipient,
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
        recipient: str,
        body: str,
        header: str | None = None,
        footer: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_cta_message",
            "cta",
            recipient,
            {
                "button_text": button_text,
                "button_url": button_url,
                "recipient": recipient,
                "body": body,
                "header": header,
                "footer": footer,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger templates.
    # ------------------------------------------------------------------ #

    async def send_text_template(
        self,
        template_name: str,
        recipient: str,
        body_parameters: list[dict] | None = None,
        language_code: str = "es",
    ) -> MessageResult:
        return await self._invoke(
            "send_text_template",
            "text_template",
            recipient,
            {
                "template_name": template_name,
                "recipient": recipient,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
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
        return await self._invoke(
            "send_media_template",
            "media_template",
            recipient,
            {
                "template_name": template_name,
                "recipient": recipient,
                "media_type": media_type,
                "media_id": media_id,
                "media_url": media_url,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
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
        return await self._invoke(
            "send_location_template",
            "location_template",
            recipient,
            {
                "template_name": template_name,
                "recipient": recipient,
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address,
                "body_parameters": body_parameters,
                "language_code": language_code,
            },
        )

    # ------------------------------------------------------------------ #
    # IMessenger specialized.
    # ------------------------------------------------------------------ #

    async def send_contact(
        self,
        contact: dict,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_contact",
            "contact",
            recipient,
            {
                "contact": contact,
                "recipient": recipient,
                "reply_to_message_id": reply_to_message_id,
            },
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
        return await self._invoke(
            "send_location",
            "location",
            recipient,
            {
                "latitude": latitude,
                "longitude": longitude,
                "recipient": recipient,
                "name": name,
                "address": address,
                "reply_to_message_id": reply_to_message_id,
            },
        )

    async def send_location_request(
        self,
        body: str,
        recipient: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        return await self._invoke(
            "send_location_request",
            "location_request",
            recipient,
            {
                "body": body,
                "recipient": recipient,
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
