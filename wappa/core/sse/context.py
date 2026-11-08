"""Request-scoped SSE event context.

Every SSE event needs the same identity signals — inbox, canonical user id,
BSUID, phone number, platform — plus optional per-request metadata like
conversation_id, chat_id, run_id, etc. Rather than thread those through every
call site (which produced v0.3.4's null-identity bugs), the framework
populates a ``ContextVar`` at each entry point (webhook, API, expiry) and
every publisher reads it at publish time.

Apps enrich the metadata bag from inside their pipeline (``update_metadata``)
and may override identity after a cache lookup (``update_identity``). The
context is automatically cleared when the entry-point scope exits.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from wappa.domain.user_identity import UserIdentity

__all__ = [
    "SSEEventContext",
    "get_sse_context",
    "update_metadata",
    "update_identity",
    "flush_incoming_sse",
    "sse_event_scope",
    "derive_identifiers",
    "classify_meta_identifier",
]

logger = logging.getLogger(__name__)


@dataclass
class SSEEventContext:
    """Per-request state shared by every SSE publisher.

    ``_pending_incoming`` + ``_pending_flush`` stage an ``incoming_message``
    payload until identity/metadata is ready; the first of
    ``update_metadata``, ``update_identity``, outgoing send, or
    ``post_process_message`` wins and emits.
    """

    inbox_id: str = "unknown"
    user_id: str = "unknown"
    bsuid: str | None = None
    phone_number: str | None = None
    platform: str | None = None
    identity: UserIdentity | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _pending_incoming: dict[str, Any] | None = None
    _pending_flush: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None
    _tracker: Any = None


_sse_event_context: ContextVar[SSEEventContext | None] = ContextVar(
    "sse_event_context", default=None
)


def get_sse_context() -> SSEEventContext | None:
    """Return the current request-scoped SSE context, or ``None`` if unset."""
    return _sse_event_context.get()


def flush_incoming_sse() -> None:
    """Emit any staged ``incoming_message`` SSE event now.

    Idempotent: the first caller claims the pending payload and schedules
    the publish as a background task; subsequent callers are no-ops. Also
    invoked automatically by ``update_metadata``, ``update_identity``, and
    the messenger wrapper before any outgoing send.
    """
    ctx = _sse_event_context.get()
    if ctx is None or ctx._pending_incoming is None or ctx._pending_flush is None:
        return
    pending = ctx._pending_incoming
    flush = ctx._pending_flush
    ctx._pending_incoming = None
    ctx._pending_flush = None
    tracker = ctx._tracker
    if tracker is not None:
        try:
            tracker.track(flush(pending), name="sse_flush_incoming")
        except RuntimeError:
            logger.debug("SSE flush skipped: runtime is draining")
    else:
        try:
            asyncio.create_task(flush(pending))
        except RuntimeError:
            logger.debug("SSE flush skipped: no running event loop")


def update_metadata(**kwargs: Any) -> None:
    """Merge values into the SSE context's metadata bag and flush any staged incoming event.

    No-op when no SSE context is active.
    """
    ctx = _sse_event_context.get()
    if ctx is None:
        return
    ctx.metadata.update(kwargs)
    flush_incoming_sse()


def update_identity(
    *,
    user_id: str | None = None,
    bsuid: str | None = None,
    phone_number: str | None = None,
) -> None:
    """Override identity fields on the SSE context and flush any staged incoming event.

    ``None`` arguments are ignored. No-op when no SSE context is active.
    """
    ctx = _sse_event_context.get()
    if ctx is None:
        return
    if user_id is not None:
        ctx.user_id = user_id
    if bsuid is not None:
        ctx.bsuid = bsuid
    if phone_number is not None:
        ctx.phone_number = phone_number
    if ctx.identity is not None:
        changed = {
            key: value
            for key, value in {
                "user_id": user_id,
                "bsuid": bsuid,
                "phone_number": phone_number,
            }.items()
            if value is not None
        }
        ctx.identity = ctx.identity.model_copy(update=changed)
    flush_incoming_sse()


def classify_meta_identifier(
    value: str | None, *, platform: str | None = None
) -> tuple[str | None, str | None]:
    """Parse phone/BSUID evidence, including Parent BSUIDs; opaque IDs are unknown.

    For a known Platform use its qualified projection rather than guessing
    numeric native IDs are phone evidence.
    """
    if not value:
        return None, None
    from wappa.domain.inbox.identity import InboxRef
    from wappa.platforms import project_identity
    from wappa.schemas.core.types import PlatformType

    if not value.strip():
        return None, None
    if platform is None:
        from wappa.schemas.core.recipient import RecipientKind, resolve_recipient

        try:
            resolved = resolve_recipient(value)
        except ValueError:
            return None, None
        return (
            (resolved.bsuid, None)
            if resolved.kind is RecipientKind.BSUID
            else (None, resolved.phone_number)
        )
    identity = project_identity(
        InboxRef(platform=PlatformType(platform), inbox_id="projection"),
        value,
        (value,),
    )
    return identity.bsuid or identity.parent_bsuid, identity.phone_number


def derive_identifiers(user_obj: Any) -> tuple[str | None, str | None]:
    """Extract ``(bsuid, phone_number)`` from a ``UserBase``-shaped object.

    Reads ``.bsuid`` and ``.phone_number`` attributes; empty strings are
    normalised to ``None``. Returns ``(None, None)`` for any object missing
    the fields.
    """
    if user_obj is None:
        return None, None
    bsuid = getattr(user_obj, "bsuid", None) or None
    phone_number = getattr(user_obj, "phone_number", None) or None
    from wappa.schemas.core.recipient import is_bsuid_digit_echo

    if phone_number and is_bsuid_digit_echo(
        phone_number, bsuid, getattr(user_obj, "parent_bsuid", None)
    ):
        phone_number = None
    return bsuid, phone_number


@asynccontextmanager
async def sse_event_scope(
    *,
    inbox_id: str = "unknown",
    user_id: str = "unknown",
    bsuid: str | None = None,
    phone_number: str | None = None,
    platform: str,
    metadata: dict[str, Any] | None = None,
    identity: UserIdentity | None = None,
    tracker: Any = None,
) -> AsyncIterator[SSEEventContext]:
    """Install an ``SSEEventContext`` for the duration of the ``async with``.

    Framework entry points (webhook controller, API dispatcher, expiry
    dispatcher) use this to guarantee every SSE event emitted from inside the
    scope carries coherent identity + metadata, and to guarantee the context
    is cleared when the scope exits — even on exceptions.
    """
    ctx = SSEEventContext(
        inbox_id=inbox_id,
        user_id=user_id,
        bsuid=bsuid,
        phone_number=phone_number,
        platform=platform,
        identity=identity,
        metadata=dict(metadata) if metadata else {},
        _tracker=tracker,
    )
    token = _sse_event_context.set(ctx)
    try:
        yield ctx
    finally:
        _sse_event_context.reset(token)


@contextmanager
def sse_identity_cleared() -> Iterator[None]:
    """Run work with no SSE identity, restoring the caller's scope on exit.

    System-scoped scheduled work has no Inbox or User; without this it would
    inherit and publish under whatever identity the caller's context carried.
    """
    token = _sse_event_context.set(None)
    try:
        yield
    finally:
        _sse_event_context.reset(token)


def api_identity(event: Any) -> UserIdentity:
    """Project API address evidence through its selected Platform at runtime."""
    from wappa.domain.inbox.identity import InboxRef
    from wappa.platforms import project_identity
    from wappa.schemas.core.types import PlatformType

    return event.identity_evidence or project_identity(
        InboxRef(platform=PlatformType(event.platform), inbox_id=event.inbox_id),
        event.user_id or event.recipient,
        (event.recipient, *event.request_payload.get("addresses", ())),
    )
