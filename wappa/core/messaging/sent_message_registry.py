"""Table Cache implementation of :class:`ISentMessageRegistry`.

One key per sent message ID in the Inbox's Table Cache scope
(``<inbox namespace>:df:wappa_sent_messages:pkid:<message_id>``), never one
growing object. Lifecycle of each key:

1. ``record`` after a confirmed send: written with a 10-minute TTL.
2. ``claim`` when its echo arrives (usually within ~1 s): the TTL drops to a
   2-minute grace period, covering a redelivered echo, then the key expires.
3. A send whose echo never arrives simply expires after 10 minutes.

So the registry holds roughly the sends of the last few seconds. On Redis it
is shared by every worker and expiry is native; the memory backend sweeps
expired keys in the background.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.interfaces.cache_interfaces import ITableCache
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry

SENT_MESSAGES_TABLE = "wappa_sent_messages"
DEFAULT_SENT_MESSAGE_TTL_SECONDS = 10 * 60
CLAIMED_GRACE_SECONDS = 2 * 60


class TableSentMessageRegistry(ISentMessageRegistry):
    def __init__(
        self,
        table_for: Callable[[InboxRef], ITableCache],
        *,
        ttl_seconds: int = DEFAULT_SENT_MESSAGE_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._table_for = table_for
        self._ttl = ttl_seconds
        self._logger = get_logger(__name__)

    async def record(self, inbox_ref: InboxRef, message_id: str) -> None:
        try:
            await self._table_for(inbox_ref).upsert(
                SENT_MESSAGES_TABLE,
                message_id,
                {"sent_at": int(time.time())},
                ttl=self._ttl,
            )
        except Exception as exc:  # never fail a send because of the registry
            self._logger.warning(
                "Sent-message registry record failed for %s: %s: %s",
                inbox_ref,
                type(exc).__name__,
                exc,
            )

    async def claim(self, inbox_ref: InboxRef, message_id: str) -> bool:
        # One round trip: shortening the TTL also proves the key exists.
        return await self._table_for(inbox_ref).renew_ttl(
            SENT_MESSAGES_TABLE, message_id, CLAIMED_GRACE_SECONDS
        )


__all__ = [
    "CLAIMED_GRACE_SECONDS",
    "DEFAULT_SENT_MESSAGE_TTL_SECONDS",
    "SENT_MESSAGES_TABLE",
    "TableSentMessageRegistry",
]
