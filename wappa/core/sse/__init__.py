"""SSE event hub and wrappers for real-time event streaming."""

from .context import (
    SSEEventContext,
    classify_meta_identifier,
    derive_identifiers,
    flush_incoming_sse,
    get_sse_context,
    sse_event_scope,
    update_identity,
    update_metadata,
)
from .event_hub import SSEEventHub, SSESubscription
from .handlers import (
    _BUILTIN_SSE_EVENT_TYPES,
    SUPPORTED_SSE_EVENT_TYPES,
    SSEErrorHandler,
    SSEEventType,
    SSEMessageHandler,
    SSEStatusHandler,
    publish_api_sse_event,
    publish_sse_event,
    register_sse_event_type,
)
from .messenger_wrapper import SSEMessengerWrapper

__all__ = [
    "SSEEventContext",
    "SSEEventHub",
    "SSESubscription",
    "SSEEventType",
    "SUPPORTED_SSE_EVENT_TYPES",
    "_BUILTIN_SSE_EVENT_TYPES",
    "register_sse_event_type",
    "SSEMessageHandler",
    "SSEStatusHandler",
    "SSEErrorHandler",
    "SSEMessengerWrapper",
    "publish_sse_event",
    "publish_api_sse_event",
    "get_sse_context",
    "update_metadata",
    "update_identity",
    "flush_incoming_sse",
    "sse_event_scope",
    "derive_identifiers",
    "classify_meta_identifier",
]
