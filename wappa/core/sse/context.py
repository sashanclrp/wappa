"""Request-scoped SSE event context.

Every SSE event needs the same identity signals — tenant, canonical user id,
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

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "SSEEventContext",
    "get_sse_context",
    "update_metadata",
    "update_identity",
    "sse_event_scope",
    "derive_identifiers",
    "classify_meta_identifier",
]

_BSUID_PATTERN = re.compile(r"^[A-Z]{2}\.[A-Za-z0-9]{1,128}$")


@dataclass
class SSEEventContext:
    """Per-request state shared by every SSE publisher.

    ``metadata`` is a mutable dict the app enriches during the pipeline.
    ``_pending_incoming`` holds the ``incoming_message`` payload between the
    default handler's ``log_incoming_message`` (where it's staged) and
    ``post_process_message`` (where it's flushed with enriched metadata).
    """

    tenant_id: str = "unknown"
    user_id: str = "unknown"
    bsuid: str | None = None
    phone_number: str | None = None
    platform: str = "whatsapp"
    metadata: dict[str, Any] = field(default_factory=dict)
    _pending_incoming: dict[str, Any] | None = None


_sse_event_context: ContextVar[SSEEventContext | None] = ContextVar(
    "sse_event_context", default=None
)


def get_sse_context() -> SSEEventContext | None:
    """Return the current request-scoped SSE context, or ``None`` if unset."""
    return _sse_event_context.get()


def update_metadata(**kwargs: Any) -> None:
    """Merge values into the current SSE context's metadata bag.

    No-op when no SSE context is active (e.g. outside a framework entry-point
    scope). Apps call this from inside the pipeline to enrich conversation,
    chat, run, and similar domain identifiers onto every SSE event.
    """
    ctx = _sse_event_context.get()
    if ctx is None:
        return
    ctx.metadata.update(kwargs)


def update_identity(
    *,
    user_id: str | None = None,
    bsuid: str | None = None,
    phone_number: str | None = None,
) -> None:
    """Override identity fields on the current SSE context.

    Useful after a cache or DB lookup promotes a wa_id-only request into a
    canonical BSUID, or when an expiry handler hydrates phone_number from
    stored user state. ``None`` arguments are ignored — only the supplied
    fields are written. No-op when no SSE context is active.
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


def classify_meta_identifier(value: str | None) -> tuple[str | None, str | None]:
    """Split a Meta identifier into ``(bsuid, phone_number)`` by shape.

    BSUIDs match ``<CC>.<alnum>{1,128}``; anything else is treated as a
    phone/wa_id. Empty values yield ``(None, None)``.
    """
    if not value:
        return None, None
    normalized = value.strip()
    if not normalized:
        return None, None
    if _BSUID_PATTERN.fullmatch(normalized):
        return normalized, None
    return None, normalized


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
    return bsuid, phone_number


@asynccontextmanager
async def sse_event_scope(
    *,
    tenant_id: str = "unknown",
    user_id: str = "unknown",
    bsuid: str | None = None,
    phone_number: str | None = None,
    platform: str = "whatsapp",
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[SSEEventContext]:
    """Install an ``SSEEventContext`` for the duration of the ``async with``.

    Framework entry points (webhook controller, API dispatcher, expiry
    dispatcher) use this to guarantee every SSE event emitted from inside the
    scope carries coherent identity + metadata, and to guarantee the context
    is cleared when the scope exits — even on exceptions.
    """
    ctx = SSEEventContext(
        tenant_id=tenant_id,
        user_id=user_id,
        bsuid=bsuid,
        phone_number=phone_number,
        platform=platform,
        metadata=dict(metadata) if metadata else {},
    )
    token = _sse_event_context.set(ctx)
    try:
        yield ctx
    finally:
        _sse_event_context.reset(token)
