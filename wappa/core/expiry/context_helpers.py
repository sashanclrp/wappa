"""
Utility functions that bootstrap messenger and cache factory instances
for use inside expiry action handlers.

Example:
    from wappa.core.expiry import (
        create_expiry_messenger,
        create_expiry_cache_factory,
        parse_inbox_from_expired_key,
    )

    @expiry_registry.on_expire_action("user_inactivity")
    async def handle_user_inactivity(identifier: str, full_key: str) -> None:
        inbox_id = parse_inbox_from_expired_key(full_key)
        user_id = identifier

        messenger = await create_expiry_messenger(inbox_id)
        cache_factory = create_expiry_cache_factory(inbox_id, user_id)
        user_cache = cache_factory.create_user_cache()
"""

from wappa.core.expiry.app_context import get_app_context
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


async def create_expiry_messenger(inbox_id: str) -> IMessenger:
    """
    Return a WhatsApp messenger for use inside an expiry handler.

    Creates a WhatsApp messenger instance using the shared HTTP session
    from FastAPI app state, following the same pattern as webhook controllers.

    This function hides the 18-line manual bootstrapping complexity,
    providing production-ready error handling with specific error types.

    Args:
        inbox_id: Inbox identifier (WhatsApp phone_number_id)

    Returns:
        Configured IMessenger instance ready for sending messages

    Raises:
        FastAPIAppNotAvailableError: If ExpiryPlugin is not configured.
        HTTPSessionNotAvailableError: If http_session is missing from app.state.
        MessengerCreationError: If the messenger factory fails.
    """
    # Get FastAPI app to access shared HTTP session
    app = get_app_context().get_app()

    if not app:
        logger.error("FastAPI app not registered - cannot create messenger")
        raise FastAPIAppNotAvailableError(
            "FastAPI app not registered - ensure ExpiryPlugin is configured"
        )

    session_lifecycle = getattr(app.state, "session_lifecycle", None)
    if not session_lifecycle:
        raise HTTPSessionNotAvailableError(
            "SessionLifecycle not available in app.state — ensure "
            "WappaCorePlugin is configured and has started"
        )

    credential_store = getattr(app.state, "inbox_credential_store", None)

    try:
        messenger_factory = MessengerFactory(
            credential_store=credential_store,
            session_provider=session_lifecycle.get_session,
        )
        messenger = await messenger_factory.create_messenger(
            platform=PlatformType.WHATSAPP,
            inbox_id=inbox_id,
        )
        logger.debug("Created expiry messenger for inbox: %s", inbox_id)
        return messenger

    except Exception as e:
        logger.error("Failed to create messenger for inbox %s: %s", inbox_id, e)
        raise MessengerCreationError(
            f"Messenger creation failed for inbox {inbox_id}: {e}"
        ) from e


def create_expiry_cache_factory(inbox_id: str, user_id: str) -> ICacheFactory:
    """
    Bootstrap cache factory for expiry handler context.

    Creates a Redis cache factory instance with the specified inbox and user context,
    following the framework's context-aware cache factory pattern.

    Args:
        inbox_id: Inbox identifier for namespace isolation
        user_id: User identifier for user-specific caches

    Returns:
        Configured ICacheFactory instance for creating context-bound caches

    Raises:
        CacheFactoryCreationError: If cache factory creation fails
        ValueError: If inbox_id or user_id is empty

    Example:
        cache_factory = create_expiry_cache_factory("wappa", "+1234567890")
        user_cache = cache_factory.create_user_cache()
        data = await user_cache.get()
    """
    if not inbox_id:
        raise ValueError("inbox_id is required for cache factory creation")
    if not user_id:
        raise ValueError("user_id is required for cache factory creation")

    try:
        cache_factory_class = create_cache_factory("redis")
        cache_factory = cache_factory_class(inbox_id=inbox_id, user_id=user_id)
        logger.debug("Created expiry cache factory for inbox: %s, user: %s", inbox_id, user_id)
        return cache_factory

    except ImportError as e:
        logger.error("Redis dependencies not available: %s", e)
        raise CacheFactoryCreationError(
            f"Redis cache factory creation failed - ensure redis dependencies are installed: {e}"
        ) from e

    except Exception as e:
        logger.error("Failed to create cache factory: %s", e)
        raise CacheFactoryCreationError(
            f"Cache factory creation failed for inbox {inbox_id}, user {user_id}: {e}"
        ) from e


def parse_inbox_from_expired_key(full_key: str) -> str:
    """
    Parse inbox ID from a Redis expiry trigger key.

    Expiry trigger keys follow the pattern: {inbox}:EXPTRIGGER:{action}:{identifier}
    This function extracts the inbox portion from the full key.

    Args:
        full_key: Complete Redis key that expired
                 (e.g., "wappa:EXPTRIGGER:user_inactivity:+1234567890")

    Returns:
        Inbox ID extracted from the key, or "wappa" as default fallback

    Example:
        >>> parse_inbox_from_expired_key("acme:EXPTRIGGER:reminder:USER123")
        "acme"
        >>> parse_inbox_from_expired_key("simple_key")
        "wappa"
    """
    if ":" in full_key:
        return full_key.split(":")[0]
    return "wappa"
