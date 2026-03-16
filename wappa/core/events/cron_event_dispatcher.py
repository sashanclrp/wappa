"""
Cron event dispatcher for scheduled background task events.

Follows Single Responsibility Principle:
- Only handles dispatching CronEvent to handlers
- Does not handle scheduling (that's fastapi-crons via CronPlugin)
- Does not handle context creation (that's WappaContextFactory)
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.domain.events.cron_event import CronEvent


class CronEventDispatcher:
    """
    Dispatches CronEvent instances to the registered WappaEventHandler.

    Receives a pre-cloned handler (with context already bound via
    with_context()) from the CronPlugin pipeline.
    """

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    async def dispatch(
        self,
        event: "CronEvent",
        request_handler: "WappaEventHandler",
    ) -> dict:
        """
        Dispatch cron event to the context-bound handler.

        Args:
            event: CronEvent from the CronPlugin pipeline
            request_handler: Context-bound handler clone (from with_context())

        Returns:
            Dict with success status and dispatch metadata
        """
        dispatch_start = datetime.now(UTC)

        try:
            self.logger.info(
                f"Dispatching cron event: {event.cron_id} "
                f"(tenant={event.tenant_id}, expr={event.cron_expr})"
            )

            await request_handler.handle_cron_event(event)

            dispatch_time = (datetime.now(UTC) - dispatch_start).total_seconds()
            self.logger.debug(f"Cron event processed in {dispatch_time:.3f}s")

            return {
                "success": True,
                "action": "cron_event_processed",
                "cron_id": event.cron_id,
                "tenant_id": event.tenant_id,
                "dispatch_time": dispatch_time,
            }

        except Exception as e:
            self.logger.error(
                f"Error dispatching cron event {event.cron_id}: {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "cron_id": event.cron_id,
            }
