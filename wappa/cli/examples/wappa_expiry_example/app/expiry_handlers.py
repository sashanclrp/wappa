"""
Expiry Action Handlers - Process expired triggers

This module registers expiry action handlers using the @expiry_registry decorator.
Handlers are automatically called when Redis keys expire (15s inactivity).

Pattern from wpDemoHotels: Use expiry triggers for inactivity detection.

This implementation uses framework context helpers for clean, production-ready code:
- create_expiry_messenger(): Bootstraps messenger with shared HTTP session
- create_expiry_cache_factory(): Creates context-bound cache factory
- format_inactivity_message_history(): Formats accumulated messages for echo response (example-specific)

Example:
    # The handler is automatically registered via decorator
    @expiry_registry.on_expire_action("user_inactivity")
    async def handle_user_inactivity(identifier: str, full_key: str) -> None:
        # Handler fires after 15 seconds of user inactivity
        pass
"""

from wappa import expiry_registry
from wappa.core.expiry import (
    CacheFactoryCreationError,
    FastAPIAppNotAvailableError,
    HTTPSessionNotAvailableError,
    MessengerCreationError,
    create_expiry_cache_factory,
    create_expiry_messenger,
    parse_tenant_from_expired_key,
)
from wappa.core.logging.logger import get_logger

from .utils import format_inactivity_message_history

logger = get_logger(__name__)


@expiry_registry.on_expire_action("user_inactivity")
async def handle_user_inactivity(identifier: str, full_key: str) -> None:
    """
    Handle user inactivity trigger - echo back all accumulated messages.

    This handler fires after 15 seconds of user inactivity. It:
    1. Retrieves all accumulated messages from UserCache
    2. Formats them with timestamps in chronological order
    3. Sends them back to the user
    4. Cleans up the UserCache

    Args:
        identifier: User ID (phone number) from the trigger key
        full_key: Complete Redis key that expired
            (e.g., "wappa:EXPTRIGGER:user_inactivity:+1234567890")

    Example:
        User sends 3 messages rapidly, then stops.
        After 15 seconds, this handler fires and echoes:
        "Message History (3 messages)
         [10:30:45] Hello
         [10:30:47] How are you?
         [10:30:50] See you later!"
    """
    user_id = identifier
    tenant_id = parse_tenant_from_expired_key(full_key)

    logger.info(
        f"User inactivity detected for {user_id} - processing accumulated messages"
    )

    # 1. Create cache factory and retrieve messages
    messages = await _retrieve_user_messages(tenant_id, user_id)
    if messages is None:
        return

    message_count = len(messages)
    if message_count == 0:
        logger.info(f"No messages to echo for user {user_id}")
        return

    logger.info(f"Echoing {message_count} message(s) to user {user_id}")

    # 2. Format message history
    echo_text = format_inactivity_message_history(messages, message_count)

    # 3. Send echo message via WhatsApp
    send_success = await _send_echo_message(tenant_id, user_id, echo_text)
    if not send_success:
        return

    # 4. Clean up user cache
    await _cleanup_user_cache(tenant_id, user_id)


async def _retrieve_user_messages(tenant_id: str, user_id: str) -> list[dict] | None:
    """
    Retrieve accumulated messages from user cache.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier

    Returns:
        List of message dictionaries, or None if retrieval failed
    """
    try:
        cache_factory = create_expiry_cache_factory(tenant_id, user_id)
        user_cache = cache_factory.create_user_cache()
        user_data = await user_cache.get()

    except CacheFactoryCreationError as e:
        logger.error(f"Cache factory creation failed: {e}")
        return None

    except Exception as e:
        logger.error(f"Failed to retrieve user data: {e}", exc_info=True)
        return None

    if not user_data or "messages" not in user_data:
        logger.warning(
            f"No messages found for user {user_id} (may have been cleaned up)"
        )
        return None

    return user_data.get("messages", [])


async def _send_echo_message(tenant_id: str, user_id: str, echo_text: str) -> bool:
    """
    Send formatted echo message to user via WhatsApp.

    Args:
        tenant_id: Tenant identifier for messenger creation
        user_id: Recipient user ID
        echo_text: Formatted message text to send

    Returns:
        True if message sent successfully, False otherwise
    """
    try:
        messenger = await create_expiry_messenger(tenant_id)

    except FastAPIAppNotAvailableError as e:
        logger.error(f"FastAPI app not available: {e}")
        return False

    except HTTPSessionNotAvailableError as e:
        logger.error(f"HTTP session not available: {e}")
        return False

    except MessengerCreationError as e:
        logger.error(f"Messenger creation failed: {e}")
        return False

    try:
        result = await messenger.send_text(recipient=user_id, text=echo_text)

        if result.success:
            logger.info(f"Successfully echoed messages to {user_id}")
            return True
        else:
            logger.error(f"Failed to send echo message to {user_id}: {result.error}")
            return False

    except Exception as e:
        logger.error(f"Error sending echo message: {e}", exc_info=True)
        return False


async def _cleanup_user_cache(tenant_id: str, user_id: str) -> None:
    """
    Clean up user cache after processing.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
    """
    try:
        cache_factory = create_expiry_cache_factory(tenant_id, user_id)
        user_cache = cache_factory.create_user_cache()
        deleted = await user_cache.delete()

        if deleted:
            logger.info(f"Cleaned up UserCache for {user_id}")
        else:
            logger.warning(f"UserCache for {user_id} was already deleted")

    except Exception as e:
        # Cache cleanup failure is non-critical - log warning, don't fail
        logger.warning(f"Failed to clean up UserCache for {user_id}: {e}")
