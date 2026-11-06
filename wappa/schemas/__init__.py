"""
Shared schema primitives for Wappa.

Inbound webhook payload schemas and Universal Models live in ``wappa.webhooks``.
This package owns cross-cutting primitives used by inbound, outbound, API, and
runtime modules, and the neutral send request models (``wappa.schemas.requests``)
shared by the HTTP routes and the outbound classifier.
"""

from .core.recipient import looks_like_bsuid

__all__ = [
    "looks_like_bsuid",
]
