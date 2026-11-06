"""Parse Redis expired-key notifications into qualified Expiry Notifications."""

import logging
from dataclasses import dataclass

from wappa.domain.inbox.identity import InboxRef
from wappa.persistence.redis.redis_handler.utils.key_factory import KeyFactory

logger = logging.getLogger(__name__)

_keys = KeyFactory()


@dataclass(frozen=True)
class ExpiryNotification:
    """The facts an Expiry Key carries once it has expired."""

    expired_key: str
    inbox_ref: InboxRef
    action: str
    identifier: str


def parse_expiry_notification(message: dict | None) -> ExpiryNotification | None:
    """Parse one Pub/Sub message; ``None`` when it is not a valid Expiry Key.

    Keys with another shape share the Redis database and are ignored. A trigger
    with an invalid Inbox namespace is logged and dropped, never given a
    fabricated scope.
    """
    if message is None or message.get("type") != "message":
        return None

    expired_key = message.get("data")
    if isinstance(expired_key, bytes):
        expired_key = expired_key.decode("utf-8")
    if not expired_key:
        return None

    parsed = _keys.parse_trigger(expired_key)
    if parsed is None:
        logger.debug("Ignoring expired key that is not a trigger: %s", expired_key)
        return None

    namespace, action, identifier = parsed
    try:
        inbox_ref = InboxRef.from_cache_namespace(namespace)
    except ValueError:
        logger.warning(
            "Dropping expiry event with invalid Inbox namespace: %s", expired_key
        )
        return None

    return ExpiryNotification(
        expired_key=expired_key,
        inbox_ref=inbox_ref,
        action=action,
        identifier=identifier,
    )
