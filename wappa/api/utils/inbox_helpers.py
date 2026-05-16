"""
Inbox context utilities for API routes.

Provides centralized inbox context retrieval to eliminate duplication
across dependency injection functions.
"""


def require_inbox_context() -> str:
    """Get current inbox context, raising ValueError if not available.

    Returns:
        The current inbox ID

    Raises:
        ValueError: If no inbox context is available
    """
    from wappa.core.logging.context import require_inbox_context as _require

    return _require()
