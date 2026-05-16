"""
Request context management using contextvars for automatic propagation.

This module provides automatic context propagation throughout the entire request lifecycle
without requiring manual parameter passing. The context is set once in middleware and
automatically available to all components.
"""

from contextvars import ContextVar

# Context variables for automatic propagation
_inbox_context: ContextVar[str | None] = ContextVar(
    "inbox_id", default=None
)  # From middleware (URL path extraction)
_user_context: ContextVar[str | None] = ContextVar(
    "user_id", default=None
)  # From webhook JSON


def set_request_context(
    inbox_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    Set the request context for the current async context.

    This should be called during request processing and will automatically
    propagate to all subsequent function calls in the same request.

    Args:
        inbox_id: Inbox identifier (platform-facing message identity)
        user_id: User identifier from webhook payload (BSUID or phone number)
    """
    if inbox_id is not None:
        _inbox_context.set(inbox_id)
    if user_id is not None:
        _user_context.set(user_id)


def get_current_inbox_context() -> str | None:
    """
    Get the current inbox ID from context variables.

    Returns:
        Current inbox ID, or None if not set
    """
    return _inbox_context.get()


def get_current_user_context() -> str | None:
    """
    Get the current user ID from context variables.

    Returns:
        Current user ID (webhook user context), or None if not set
    """
    return _user_context.get()


def require_inbox_context() -> str:
    """Get current inbox context, raising ValueError if not available.

    Returns:
        The current inbox ID

    Raises:
        ValueError: If no inbox context is available
    """
    inbox_id = get_current_inbox_context()
    if not inbox_id:
        raise ValueError("No inbox context available - check middleware configuration")
    return inbox_id


def clear_request_context() -> None:
    """
    Clear the request context.

    This is typically not needed as context is automatically isolated
    per request, but can be useful for testing.
    """
    _inbox_context.set(None)
    _user_context.set(None)


def get_context_info() -> dict[str, str | None]:
    """
    Get current context information for debugging.

    Returns:
        Dictionary with current inbox_id and user_id
    """
    return {
        "inbox_id": get_current_inbox_context(),
        "user_id": get_current_user_context(),
    }
