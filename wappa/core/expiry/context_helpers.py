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
from wappa.domain.inbox.errors import InboxDirectoryError
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.cache_factory import ICacheFactory
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.persistence.cache_factory import create_cache_factory

logger = get_logger(__name__)


class ExpiryContextError(Exception):
    """Raised when expiry handler context cannot be established."""

    pass


class FastAPIAppNotAvailableError(ExpiryContextError):
    """Raised when FastAPI app is not available for expiry context."""

    pass


class SessionLifecycleNotAvailableError(ExpiryContextError):
    """Raised when Wappa's session lifecycle is unavailable."""

    pass


class MessengerCreationError(ExpiryContextError):
    """Raised when messenger creation fails."""

    pass


class CacheFactoryCreationError(ExpiryContextError):
    """Raised when cache factory creation fails."""

    pass


def _as_inbox_ref(inbox: InboxRef | str) -> InboxRef:
    """Accept the legacy raw WhatsApp argument while preserving qualified scope."""
    return inbox if isinstance(inbox, InboxRef) else InboxRef.whatsapp(inbox)


async def create_expiry_messenger(inbox: InboxRef | str) -> IMessenger:
    """
    Return a WhatsApp messenger for use inside an expiry handler.

    Creates a WhatsApp messenger through the lifecycle owner registered by the
    core plugin.

    This function hides the 18-line manual bootstrapping complexity,
    providing production-ready error handling with specific error types.

    Args:
        inbox: Qualified Inbox identity. A raw string remains a legacy WhatsApp
            convenience input.

    Returns:
        Configured IMessenger instance ready for sending messages

    Raises:
        FastAPIAppNotAvailableError: If ExpiryPlugin is not configured.
        SessionLifecycleNotAvailableError: If the lifecycle owner is unavailable.
        MessengerCreationError: If the messenger factory fails.
    """
    # AppContext provides access to the core plugin's lifecycle owner.
    inbox_ref = _as_inbox_ref(inbox)
    app = get_app_context().get_app()

    if not app:
        logger.error("FastAPI app not registered - cannot create messenger")
        raise FastAPIAppNotAvailableError(
            "FastAPI app not registered - ensure ExpiryPlugin is configured"
        )

    from wappa.core.dispatch.context_builder import DispatchContextBuilder

    session_lifecycle = getattr(app.state, "session_lifecycle", None)
    if not session_lifecycle:
        raise SessionLifecycleNotAvailableError(
            "SessionLifecycle not available in app.state — ensure "
            "WappaCorePlugin is configured and has started"
        )

    try:
        builder = DispatchContextBuilder.from_app(app)
        messenger = await builder.messenger_factory.create_messenger(inbox_ref)
        logger.debug("Created expiry messenger for inbox: %s", inbox_ref)
        return messenger

    except InboxDirectoryError:
        raise
    except Exception as e:
        logger.error("Failed to create messenger for inbox %s: %s", inbox_ref, e)
        raise MessengerCreationError(
            f"Messenger creation failed for inbox {inbox_ref}: {e}"
        ) from e


def create_expiry_cache_factory(inbox: InboxRef | str, user_id: str) -> ICacheFactory:
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
    inbox_ref = _as_inbox_ref(inbox)
    if not user_id:
        raise ValueError("user_id is required for cache factory creation")

    try:
        cache_factory_class = create_cache_factory("redis")
        cache_factory = cache_factory_class(
            inbox_id=inbox_ref.cache_namespace, user_id=user_id
        )
        logger.debug(
            "Created expiry cache factory for inbox: %s, user: %s", inbox_ref, user_id
        )
        return cache_factory

    except ImportError as e:
        logger.error("Redis dependencies not available: %s", e)
        raise CacheFactoryCreationError(
            f"Redis cache factory creation failed - ensure redis dependencies are installed: {e}"
        ) from e

    except Exception as e:
        logger.error("Failed to create cache factory: %s", e)
        raise CacheFactoryCreationError(
            f"Cache factory creation failed for inbox {inbox_ref}, user {user_id}: {e}"
        ) from e


def parse_inbox_from_expired_key(full_key: str) -> str | None:
    """
    Parse inbox ID from a Redis expiry trigger key.

    Expiry trigger keys follow the pattern: {inbox}:EXPTRIGGER:{action}:{identifier}
    This function extracts the inbox portion from the full key.

    Args:
        full_key: Complete Redis key that expired
                 (e.g., "wappa:EXPTRIGGER:user_inactivity:+1234567890")

    Returns:
        Inbox namespace extracted from a valid key, otherwise ``None``.

    Example:
        >>> parse_inbox_from_expired_key("acme:EXPTRIGGER:reminder:USER123")
        "acme"
        >>> parse_inbox_from_expired_key("simple_key") is None
        True
    """
    inbox_ref = parse_inbox_ref_from_expired_key(full_key)
    return inbox_ref.cache_namespace if inbox_ref is not None else None


def parse_inbox_ref_from_expired_key(full_key: str) -> InboxRef | None:
    """Return the qualified Inbox identity encoded in a valid expiry key.

    Invalid keys are rejected rather than assigned a fabricated default scope.
    """
    from wappa.persistence.redis.redis_handler.utils.key_factory import KeyFactory

    parsed = KeyFactory().parse_trigger(full_key)
    if parsed is None:
        return None
    namespace, _, _ = parsed
    try:
        return InboxRef.from_cache_namespace(namespace)
    except ValueError:
        return None
