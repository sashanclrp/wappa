"""
External event dispatcher for non-messaging-platform webhook events.

Follows Single Responsibility Principle:
- Only handles dispatching ExternalEvent to handlers
- Does not handle webhook parsing (that's IWebhookProcessor)
- Does not handle context creation (that's WappaContextFactory)
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.domain.events.external_event import ExternalEvent


class ExternalEventDispatcher:
    """
    Dispatches ExternalEvent instances to the registered WappaEventHandler.

    Unlike APIEventDispatcher which creates handler clones internally,
    this dispatcher receives a pre-cloned handler (with context already
    bound via with_context()) from the WebhookPlugin pipeline.
    """

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    async def dispatch(
        self,
        event: "ExternalEvent",
        request_handler: "WappaEventHandler",
    ) -> dict:
        """
        Dispatch external event to the context-bound handler.

        Args:
            event: ExternalEvent from IWebhookProcessor.parse_event()
            request_handler: Context-bound handler clone (from with_context())

        Returns:
            Dict with success status and dispatch metadata
        """
        dispatch_start = datetime.now(UTC)

        try:
            self.logger.info(
                f"Dispatching external event: {event.source}/{event.event_type} "
                f"(tenant={event.tenant_id}, user={event.user_id})"
            )

            await request_handler.handle_external_event(event)

            dispatch_time = (datetime.now(UTC) - dispatch_start).total_seconds()
            self.logger.debug(f"External event processed in {dispatch_time:.3f}s")

            return {
                "success": True,
                "action": "external_event_processed",
                "source": event.source,
                "event_type": event.event_type,
                "tenant_id": event.tenant_id,
                "user_id": event.user_id,
                "dispatch_time": dispatch_time,
            }

        except Exception as e:
            self.logger.error(
                f"Error dispatching external event "
                f"{event.source}/{event.event_type}: {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "source": event.source,
                "event_type": event.event_type,
            }
