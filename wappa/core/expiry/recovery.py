"""Bounded recovery of durable overdue Redis expiry occurrences."""

from __future__ import annotations

import asyncio
import logging

from wappa.persistence.redis.expiry_index import RedisExpiryIndex

from .dispatcher import ExpiryDispatcher
from .parser import parse_expiry_notification

logger = logging.getLogger(__name__)


class ExpiryRecovery:
    """One admission path for Pub/Sub and periodic due-index recovery.

    A claim suppresses concurrent admission for 30 seconds, not forever. Long
    handlers may be delivered again; the Host owns idempotent side effects.
    """

    def __init__(
        self,
        index: RedisExpiryIndex,
        dispatcher: ExpiryDispatcher,
        *,
        batch_size: int = 100,
        interval: float = 2.0,
    ) -> None:
        if batch_size <= 0 or interval <= 0:
            raise ValueError("Expiry recovery batch size and interval must be positive")
        self.index = index
        self.dispatcher = dispatcher
        self.batch_size = batch_size
        self.interval = interval
        self._inflight: dict[str, asyncio.Task[None]] = {}

    async def deliver(self, key: str, *, recovered: bool) -> None:
        if key in self._inflight or (
            recovered and len(self._inflight) >= self.batch_size
        ):
            return  # indexed work remains durable for a later tick
        trigger = await self.index.claim(key)
        if trigger is None or (recovered and trigger.record is None):
            return
        if trigger.record is not None and len(self._inflight) >= self.batch_size:
            return  # indexed Pub/Sub overflow remains recoverable after its claim
        notification = parse_expiry_notification({"type": "message", "data": key})
        if notification is None:
            await self.index.acknowledge(trigger)
            return

        async def acknowledge() -> None:
            await self.index.acknowledge(trigger)

        task = self.dispatcher.dispatch(
            notification,
            recovered=recovered,
            scheduled_for=trigger.due_at,
            execution_id=trigger.generation,
            on_success=acknowledge,
        )
        self._inflight[key] = task
        task.add_done_callback(lambda _: self._inflight.pop(key, None))

    async def tick(self) -> None:
        capacity = self.batch_size - len(self._inflight)
        if capacity <= 0:
            return
        for key in await self.index.due(capacity):
            await self.deliver(key, recovered=True)

    async def run(self) -> None:
        # First tick is immediate, including after process restart.
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Expiry recovery tick failed; indexed work retained")
            await asyncio.sleep(self.interval)
