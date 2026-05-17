"""
Shared schema primitives for Wappa.

Inbound webhook payload schemas and Universal Models live in ``wappa.webhooks``.
This package only owns cross-cutting primitives used by inbound, outbound,
API, and runtime modules.
"""

from .core.recipient import looks_like_bsuid

__all__ = [
    "looks_like_bsuid",
]
