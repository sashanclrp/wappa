"""
Request context management using contextvars for automatic propagation.

This module provides automatic context propagation throughout the entire request lifecycle
without requiring manual parameter passing. The context is set once in middleware and
automatically available to all components.
"""

from contextvars import ContextVar, Token

# Context variables for automatic propagation
_inbox_context: ContextVar[str | None] = ContextVar(
    "inbox_id", default=None
)  # From HTTP middleware or payload-routed Dispatch Context construction
_user_context: ContextVar[str | None] = ContextVar(
    "user_id", default=None
)  # From webhook JSON
_request_id_context: ContextVar[str | None] = ContextVar(
    "request_id", default=None
)  # From RequestIdMiddleware (inbound header or generated)


def set_request_context(
    inbox_id: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """
    Set the request context for the current async context.

    This should be called during request processing and will automatically
    propagate to all subsequent function calls in the same request.

    Args:
        inbox_id: Inbox identifier (platform-facing message identity)
        user_id: User identifier from webhook payload (BSUID or phone number)
        request_id: Correlation identifier for the current HTTP request
    """
    if inbox_id is not None:
        _inbox_context.set(inbox_id)
    if user_id is not None:
        _user_context.set(user_id)
    if request_id is not None:
        _request_id_context.set(request_id)


def get_current_inbox_context() -> str | None:
    """
    Get the current inbox ID from context variables.

    Returns:
        Current inbox ID, or None if not set
    """
    return _inbox_context.get()


def bind_inbox_context(inbox_id: str | None) -> Token[str | None]:
    """Bind Inbox scope for one request and return its reset token."""
    return _inbox_context.set(inbox_id)


def reset_inbox_context(token: Token[str | None]) -> None:
    """Restore the Inbox scope that existed before request handling."""
    _inbox_context.reset(token)


def bind_user_context(user_id: str | None) -> Token[str | None]:
    """Bind User scope for one unit of work and return its reset token."""
    return _user_context.set(user_id)


def reset_user_context(token: Token[str | None]) -> None:
    """Restore the User scope that existed before the bound work."""
    _user_context.reset(token)


def get_current_user_context() -> str | None:
    """
    Get the current user ID from context variables.

    Returns:
        Current user ID (webhook user context), or None if not set
    """
    return _user_context.get()


def get_current_request_id() -> str | None:
    """
    Get the correlation ID of the HTTP request being processed.

    Returns:
        Current request ID, or None when no request scope is active
        (background work, expiry handlers, cron jobs)
    """
    return _request_id_context.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Set the request ID for the current context, returning a reset token.

    Intended for the middleware that owns the request scope. Pair with
    :func:`reset_request_id` in a ``finally`` block so the previous value
    (typically ``None``) is restored rather than cleared unconditionally —
    unlike :func:`clear_request_context`, this does not disturb the inbox and
    user context set by other middleware in the same scope.
    """
    return _request_id_context.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request ID context to its value before :func:`bind_request_id`."""
    _request_id_context.reset(token)


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
    _request_id_context.set(None)


def get_context_info() -> dict[str, str | None]:
    """
    Get current context information for debugging.

    Returns:
        Dictionary with current inbox_id, user_id and request_id
    """
    return {
        "inbox_id": get_current_inbox_context(),
        "user_id": get_current_user_context(),
        "request_id": get_current_request_id(),
    }
