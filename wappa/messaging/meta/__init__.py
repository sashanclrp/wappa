"""Meta-level pieces shared by every Meta Platform adapter (WhatsApp, Instagram)."""

from .graph import (
    GraphResponse,
    MetaGraphClient,
    MetaGraphError,
    graph_request,
    meta_code_head,
    meta_error_code,
)

__all__ = [
    "GraphResponse",
    "MetaGraphClient",
    "MetaGraphError",
    "graph_request",
    "meta_code_head",
    "meta_error_code",
]
