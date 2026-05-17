"""
Wappa SSE (Server-Sent Events) — public convenience re-exports.

Canonical import surface for host applications:
    from wappa.sse import publish_sse_event, sse_event_scope
"""

from wappa.core.sse import (
    SSEEventHub,
    SSEEventType,
    SSESubscription,
    classify_meta_identifier,
    derive_identifiers,
    flush_incoming_sse,
    get_sse_context,
    publish_api_sse_event,
    publish_sse_event,
    register_sse_event_type,
    sse_event_scope,
    update_identity,
    update_metadata,
)

__all__ = [
    "classify_meta_identifier",
    "derive_identifiers",
    "flush_incoming_sse",
    "get_sse_context",
    "publish_api_sse_event",
    "publish_sse_event",
    "register_sse_event_type",
    "sse_event_scope",
    "SSEEventHub",
    "SSEEventType",
    "SSESubscription",
    "update_identity",
    "update_metadata",
]
