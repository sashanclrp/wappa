"""
Wappa API — public convenience re-exports.

Canonical import surface for host applications:
    from wappa.api import TemplateStateService, convert_body_parameters
"""

from .services.template_state_service import TemplateStateService
from .utils import (
    convert_body_parameters,
    dispatch_message_event,
    fire_api_event,
    raise_for_failed_result,
    require_inbox_context,
)
from .utils.event_decorators import resolve_event_user_id

__all__ = [
    "TemplateStateService",
    "convert_body_parameters",
    "dispatch_message_event",
    "fire_api_event",
    "raise_for_failed_result",
    "require_inbox_context",
    "resolve_event_user_id",
]
