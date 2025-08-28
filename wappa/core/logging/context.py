"""
Request context management using contextvars for automatic propagation.

This module provides automatic context propagation throughout the entire request lifecycle
without requiring manual parameter passing. The context is set once in middleware and
automatically available to all components.
"""

from contextvars import ContextVar

# Context variables for automatic propagation
_owner_context: ContextVar[str | None] = ContextVar(
    "owner_id", default=None
)  # From middleware/configuration
_tenant_context: ContextVar[str | None] = ContextVar(
    "tenant_id", default=None
)  # From webhook JSON
_user_context: ContextVar[str | None] = ContextVar(
    "user_id", default=None
)  # From webhook JSON


def set_request_context(
    owner_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """
    Set the request context for the current async context.

    This should be called during request processing and will automatically
    propagate to all subsequent function calls in the same request.

    Args:
        owner_id: Owner identifier from configuration (WhatsApp Business Account owner)
        tenant_id: Tenant identifier from webhook payload (runtime business context)
        user_id: User identifier from webhook payload (WhatsApp phone number, etc.)
    """
    if owner_id is not None:
        _owner_context.set(owner_id)
    if tenant_id is not None:
        _tenant_context.set(tenant_id)
    if user_id is not None:
        _user_context.set(user_id)


def get_current_owner_context() -> str | None:
    """
    Get the current owner ID from context variables.

    Returns:
        Current owner ID (configuration context), or None if not set
    """
    return _owner_context.get()


def get_current_tenant_context() -> str | None:
    """
    Get the current tenant ID from context variables.

    Returns:
        Current tenant ID (webhook business context), or None if not set
    """
    return _tenant_context.get()


def get_current_user_context() -> str | None:
    """
    Get the current user ID from context variables.

    Returns:
        Current user ID (webhook user context), or None if not set
    """
    return _user_context.get()


def clear_request_context() -> None:
    """
    Clear the request context.

    This is typically not needed as context is automatically isolated
    per request, but can be useful for testing.
    """
    _owner_context.set(None)
    _tenant_context.set(None)
    _user_context.set(None)


def get_context_info() -> dict[str, str | None]:
    """
    Get current context information for debugging.

    Returns:
        Dictionary with current owner_id, tenant_id and user_id
    """
    return {
        "owner_id": get_current_owner_context(),
        "tenant_id": get_current_tenant_context(),
        "user_id": get_current_user_context(),
    }
