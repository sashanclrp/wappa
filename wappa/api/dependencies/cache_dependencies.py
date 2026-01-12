"""
Cache dependency injection for API routes.

Provides cache factory access for API-level state management.
This enables features like template state management where we need
to set user state when sending messages via the REST API.
"""

from fastapi import Request

from wappa.api.services.handler_state_service import HandlerStateService
from wappa.api.services.template_state_service import TemplateStateService
from wappa.core.logging.context import get_current_tenant_context
from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.persistence.cache_factory import create_cache_factory

logger = get_logger(__name__)


async def get_cache_factory(
    request: Request, recipient: str | None = None
) -> ICacheFactory:
    """
    Get cache factory for API routes.

    Creates a tenant-scoped cache factory for state management.
    For API routes (unlike webhooks), the user_id is the message recipient.

    Args:
        request: FastAPI request object
        recipient: Optional recipient phone number for user-scoped caches

    Returns:
        ICacheFactory instance with tenant context

    Raises:
        RuntimeError: If cache factory cannot be created
    """
    try:
        # Get cache type from app state (set by WappaCorePlugin)
        cache_type = getattr(request.app.state, "wappa_cache_type", "memory")
        tenant_id = get_current_tenant_context()

        if not tenant_id:
            raise RuntimeError("No tenant context available for cache factory")

        # For API routes, user_id is the recipient phone number
        # If not provided, use a placeholder that will be replaced per operation
        user_id = recipient or "api-route"

        factory_class = create_cache_factory(cache_type)
        return factory_class(tenant_id=tenant_id, user_id=user_id)

    except Exception as e:
        logger.error(f"Failed to create cache factory: {e}")
        raise RuntimeError(f"Cache factory creation failed: {e}") from e


async def get_template_state_service(
    request: Request,
) -> TemplateStateService:
    """
    Get template state service with cache factory.

    Creates a TemplateStateService instance with a cache factory configured
    for the current request context. The recipient will be set when the
    service methods are called.

    Args:
        request: FastAPI request object

    Returns:
        TemplateStateService instance
    """
    # For template state service, we use a placeholder user_id
    # The actual recipient is passed to the service methods
    cache_factory = await get_cache_factory(request, recipient="template-api")
    return TemplateStateService(cache_factory)


async def get_handler_state_service(
    request: Request,
) -> HandlerStateService:
    """
    Get handler state service with cache factory.

    Creates a HandlerStateService instance with a cache factory configured
    for the current request context. The recipient will be set when the
    service methods are called.

    Args:
        request: FastAPI request object

    Returns:
        HandlerStateService instance
    """
    # For handler state service, we use a placeholder user_id
    # The actual recipient is passed to the service methods
    cache_factory = await get_cache_factory(request, recipient="handler-api")
    return HandlerStateService(cache_factory)
