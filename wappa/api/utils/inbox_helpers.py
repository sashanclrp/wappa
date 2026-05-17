"""
Inbox context utilities for API routes.

Provides centralized inbox context retrieval to eliminate duplication
across dependency injection functions.
"""

from wappa.core.logging.context import require_inbox_context

__all__ = ["require_inbox_context"]
