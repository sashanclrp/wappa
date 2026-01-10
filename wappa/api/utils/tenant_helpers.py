"""
Tenant context utilities for WhatsApp API routes.

Provides centralized tenant context retrieval to eliminate duplication
across dependency injection functions.
"""


def require_tenant_context() -> str:
    """Get current tenant context, raising ValueError if not available.

    Centralizes the common pattern of getting tenant context and
    raising an error if it's not set.

    Returns:
        The current tenant ID

    Raises:
        ValueError: If no tenant context is available
    """
    from wappa.core.logging.context import get_current_tenant_context

    tenant_id = get_current_tenant_context()
    if not tenant_id:
        raise ValueError("No tenant context available - check middleware configuration")
    return tenant_id
