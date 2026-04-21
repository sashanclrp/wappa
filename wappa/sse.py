"""Public SSE API surface for Wappa apps.

Apps import helpers from here to enrich the request-scoped SSE context:

    from wappa.sse import update_metadata, update_identity, get_context

    await cache.load()
    update_metadata(conversation_id=conv.id, chat_id=chat.id)
    update_identity(bsuid=user.bsuid, phone_number=user.phone_number)

Every SSE event emitted by the framework (``incoming_message``,
``outgoing_bot_message``, ``status_change``, ``webhook_error``,
``outgoing_api_message``) inside the current request scope will pick up
these fields automatically — the app never touches the event envelope.
"""

from .core.sse.context import (
    SSEEventContext,
    classify_meta_identifier,
    derive_identifiers,
    flush_incoming_sse,
    get_sse_context,
    sse_event_scope,
    update_identity,
    update_metadata,
)

#: Alias with an app-friendlier name than the internal ``get_sse_context``.
get_context = get_sse_context

__all__ = [
    "SSEEventContext",
    "get_context",
    "update_metadata",
    "update_identity",
    "flush_incoming_sse",
    "sse_event_scope",
    "derive_identifiers",
    "classify_meta_identifier",
]
