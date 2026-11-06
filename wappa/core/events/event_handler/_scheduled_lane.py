"""Scheduled event lane of ``WappaEventHandler``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._state import _HandlerState

if TYPE_CHECKING:
    from wappa.domain.events.scheduled_event import ScheduledEvent


class _ScheduledLane(_HandlerState):
    """Scheduled event lane of ``WappaEventHandler``."""

    # =========== SCHEDULED EVENT HANDLING ===========

    async def handle_scheduled_event(self, event: ScheduledEvent) -> None:
        """
        Handle a Scheduled Event using Template Method pattern.

        Every trigger source reaches this one lane: Redis expiry, built-in
        static crons, and Host schedulers through ``Scheduling.dispatch``:
        1. Pre-processing: Framework logging
        2. User processing: Custom business logic (process_scheduled_event)
        3. Post-processing: Framework cleanup

        DO NOT OVERRIDE - implement process_scheduled_event() instead.

        Args:
            event: ScheduledEvent carrying the action, its scope and source
        """
        await self._pre_process_scheduled_event(event)
        await self.process_scheduled_event(event)
        await self._post_process_scheduled_event(event)

    async def process_scheduled_event(self, event: ScheduledEvent) -> None:
        """
        Process a Scheduled Task with custom business logic.

        Optional method - override it and route by ``event.action``. This clone
        is fresh and already prepared for the event's scope:

        - Inbox and User: ``self.messenger``, ``self.whatsapp`` or
          ``self.instagram``, ``self.cache_factory``, canonical ``self.user_id``
        - Inbox only: the Messengers; no User and no ``self.cache_factory``
        - System: neither; only the database factories

        ``self.db`` and ``self.db_read`` are set whenever the database plugin is
        configured. Build typed Host dependencies once here, then route. A raised
        exception reaches an awaiting scheduler; Redis expiry logs it.

        Default: no-op (does nothing unless overridden).

        Args:
            event: ScheduledEvent with action, source, identifier and payload

        Example:
            async def process_scheduled_event(self, event: ScheduledEvent) -> None:
                match event.action:
                    case "appointment_reminder":
                        await self.messenger.send_text(
                            text="See you tomorrow!",
                            target=DirectMessage(
                                inbox_ref=self.inbox_ref,
                                addresses=DeliveryAddresses.of(self.user_id),
                            ),
                        )
                    case "cleanup_sessions":
                        async with self.db() as session:
                            await cleanup_expired(session)
        """
        _ = event
        return None

    async def _pre_process_scheduled_event(self, event: ScheduledEvent) -> None:
        """Pre-processing hook for Scheduled Events. Override to customize."""
        self.logger.debug(
            f"Scheduled event: {event.action} from {event.source} "
            f"(inbox={self.inbox_id}, user={self.user_id})"
        )

    async def _post_process_scheduled_event(self, event: ScheduledEvent) -> None:
        """Post-processing hook for Scheduled Events. Override to customize."""
        _ = event
        return None
