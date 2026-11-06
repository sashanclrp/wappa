"""
API utility functions and helpers.

Provides common functionality for route handlers including:
- Error handling helpers
- Response mapping utilities
- Inbox context utilities
- Event dispatch decorators
"""

from .error_helpers import (
    direct_target,
    map_error_to_status,
    map_send_errors,
    raise_for_failed_result,
    raise_if_rate_limited,
)
from .event_decorators import dispatch_message_event, fire_api_event
from .inbox_helpers import require_inbox_context
from .response_helpers import (
    convert_body_parameters,
    convert_buttons_to_dict,
    convert_list_sections_to_dict,
)

__all__ = [
    "convert_body_parameters",
    "convert_buttons_to_dict",
    "convert_list_sections_to_dict",
    "direct_target",
    "dispatch_message_event",
    "fire_api_event",
    "map_error_to_status",
    "map_send_errors",
    "raise_for_failed_result",
    "raise_if_rate_limited",
    "require_inbox_context",
]
