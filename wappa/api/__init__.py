"""
Wappa API — public convenience re-exports.

Canonical import surface for host applications:
    from wappa.api import convert_body_parameters, raise_for_failed_result

``TemplateStateService`` is WhatsApp-only and imports from
``wappa.messaging.whatsapp.capabilities.templates``.
"""

from .utils import (
    convert_body_parameters,
    dispatch_message_event,
    fire_api_event,
    raise_for_failed_result,
    require_inbox_context,
)
from .utils.event_decorators import resolve_event_user_id

__all__ = [
    "convert_body_parameters",
    "dispatch_message_event",
    "fire_api_event",
    "raise_for_failed_result",
    "require_inbox_context",
    "resolve_event_user_id",
]
