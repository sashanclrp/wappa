"""
Context helpers for expiry action handlers.

Provides utility functions to bootstrap messenger and cache factory instances
for expiry handler context, hiding the manual bootstrapping complexity.

These helpers enable expiry handlers to use framework patterns with minimal boilerplate,
matching the production quality standards of WappaEventHandler implementations.

Example:
    from wappa.core.expiry import (
        create_expiry_messenger,
        create_expiry_cache_factory,
        parse_tenant_from_expired_key,
    )

    @expiry_registry.on_expire_action("user_inactivity")
    async def handle_user_inactivity(identifier: str, full_key: str) -> None:
        tenant_id = parse_tenant_from_expired_key(full_key)
        user_id = identifier

        messenger = await create_expiry_messenger(tenant_id)
        cache_factory = create_expiry_cache_factory(tenant_id, user_id)
        user_cache = cache_factory.create_user_cache()

        # Business logic here...
"""

from wappa.core.expiry.listener import get_fastapi_app
from wappa.core.logging.logger import get_logger
from wappa.domain.factories.messenger_factory import MessengerFactory
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.persistence.cache_factory import create_cache_factory
from wappa.schemas.core.types import PlatformType

logger = get_logger(__name__)


class ExpiryContextError(Exception):
    """Raised when expiry handler context cannot be established."""

    pass


class FastAPIAppNotAvailableError(ExpiryContextError):
    """Raised when FastAPI app is not available for expiry context."""

    pass


class HTTPSessionNotAvailableError(ExpiryContextError):
    """Raised when HTTP session is not available in app state."""

    pass


class MessengerCreationError(ExpiryContextError):
    """Raised when messenger creation fails."""

    pass


class CacheFactoryCreationError(ExpiryContextError):
    """Raised when cache factory creation fails."""

    pass


async def create_expiry_messenger(tenant_id: str) -> IMessenger:
    """
    Bootstrap messenger for expiry handler context.

    Creates a WhatsApp messenger instance using the shared HTTP session
    from FastAPI app state, following the same pattern as webhook controllers.

    This function hides the 18-line manual bootstrapping complexity,
    providing production-ready error handling with specific error types.

    Args:
        tenant_id: Tenant identifier (WhatsApp phone_number_id)

    Returns:
        Configured IMessenger instance ready for sending messages

    Raises:
        FastAPIAppNotAvailableError: If FastAPI app is not registered
        HTTPSessionNotAvailableError: If HTTP session is not in app state
        MessengerCreationError: If messenger factory fails to create messenger

    Example:
        messenger = await create_expiry_messenger("wappa")
        await messenger.send_text(recipient="+1234567890", text="Hello!")
    """
    # Get FastAPI app to access shared HTTP session
    try:
        app = get_fastapi_app()
    except Exception as e:
        logger.error(f"Failed to get FastAPI app: {e}")
        raise FastAPIAppNotAvailableError(
            "FastAPI app not available - expiry listener may not be properly initialized"
        ) from e

    if not app:
        logger.error("FastAPI app not registered - cannot create messenger")
        raise FastAPIAppNotAvailableError(
            "FastAPI app not registered - call set_fastapi_app() during app startup"
        )

    # Get shared HTTP session from app state (for connection pooling)
    http_session = getattr(app.state, "http_session", None)
    if not http_session:
        logger.error("HTTP session not available in app state")
        raise HTTPSessionNotAvailableError(
            "HTTP session not available - ensure http_session is set in app.state during startup"
        )

    # Create messenger factory with shared HTTP session
    try:
        messenger_factory = MessengerFactory(http_session)
        messenger = await messenger_factory.create_messenger(
            platform=PlatformType.WHATSAPP,
            tenant_id=tenant_id,
        )
        logger.debug(f"Created expiry messenger for tenant: {tenant_id}")
        return messenger

    except Exception as e:
        logger.error(f"Failed to create messenger for tenant {tenant_id}: {e}")
        raise MessengerCreationError(
            f"Messenger creation failed for tenant {tenant_id}: {e}"
        ) from e


def create_expiry_cache_factory(tenant_id: str, user_id: str) -> ICacheFactory:
    """
    Bootstrap cache factory for expiry handler context.

    Creates a Redis cache factory instance with the specified tenant and user context,
    following the framework's context-aware cache factory pattern.

    Args:
        tenant_id: Tenant identifier for namespace isolation
        user_id: User identifier for user-specific caches

    Returns:
        Configured ICacheFactory instance for creating context-bound caches

    Raises:
        CacheFactoryCreationError: If cache factory creation fails
        ValueError: If tenant_id or user_id is empty

    Example:
        cache_factory = create_expiry_cache_factory("wappa", "+1234567890")
        user_cache = cache_factory.create_user_cache()
        data = await user_cache.get()
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for cache factory creation")
    if not user_id:
        raise ValueError("user_id is required for cache factory creation")

    try:
        cache_factory_class = create_cache_factory("redis")
        cache_factory = cache_factory_class(tenant_id=tenant_id, user_id=user_id)
        logger.debug(
            f"Created expiry cache factory for tenant: {tenant_id}, user: {user_id}"
        )
        return cache_factory

    except ImportError as e:
        logger.error(f"Redis dependencies not available: {e}")
        raise CacheFactoryCreationError(
            f"Redis cache factory creation failed - ensure redis dependencies are installed: {e}"
        ) from e

    except Exception as e:
        logger.error(f"Failed to create cache factory: {e}")
        raise CacheFactoryCreationError(
            f"Cache factory creation failed for tenant {tenant_id}, user {user_id}: {e}"
        ) from e


def parse_tenant_from_expired_key(full_key: str) -> str:
    """
    Parse tenant ID from a Redis expiry trigger key.

    Expiry trigger keys follow the pattern: {tenant}:EXPTRIGGER:{action}:{identifier}
    This function extracts the tenant portion from the full key.

    Args:
        full_key: Complete Redis key that expired
                 (e.g., "wappa:EXPTRIGGER:user_inactivity:+1234567890")

    Returns:
        Tenant ID extracted from the key, or "wappa" as default fallback

    Example:
        >>> parse_tenant_from_expired_key("acme:EXPTRIGGER:reminder:USER123")
        "acme"
        >>> parse_tenant_from_expired_key("simple_key")
        "wappa"
    """
    if ":" in full_key:
        return full_key.split(":")[0]
    return "wappa"
