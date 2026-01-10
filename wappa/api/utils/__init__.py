"""
API utility functions and helpers.

Provides common functionality for route handlers including:
- Error handling helpers
- Response mapping utilities
- Tenant context utilities
"""

from .error_helpers import (
    handle_messaging_result,
    map_error_to_status,
    map_whatsapp_api_error_to_status,
    raise_for_failed_result,
)
from .response_helpers import (
    convert_body_parameters,
    convert_buttons_to_dict,
    convert_header_to_dict,
    convert_list_sections_to_dict,
)
from .tenant_helpers import require_tenant_context

__all__ = [
    "handle_messaging_result",
    "map_error_to_status",
    "map_whatsapp_api_error_to_status",
    "raise_for_failed_result",
    "convert_body_parameters",
    "convert_buttons_to_dict",
    "convert_header_to_dict",
    "convert_list_sections_to_dict",
    "require_tenant_context",
]
