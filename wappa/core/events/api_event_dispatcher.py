"""
API event dispatcher for outgoing message events.

Follows Single Responsibility Principle:
- Only handles dispatching API events to handlers
- Does not handle webhook events (that's WappaEventDispatcher)
"""

from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.domain.events.api_message_event import APIMessageEvent

if TYPE_CHECKING:
    from wappa.core.events.event_handler import WappaEventHandler


class APIEventDispatcher:
    """
    Dispatches API message events to the registered event handler.

    This dispatcher follows the Observer pattern - it observes API calls
    and notifies the registered WappaEventHandler when messages are sent.

    Example:
        dispatcher = APIEventDispatcher(event_handler)

        # After sending a message via API:
        event = APIMessageEvent(
            message_type="text",
            recipient="1234567890",
            request_payload={...},
            response_success=True,
            message_id="wamid.xxx",
            tenant_id="tenant-123",
        )
        await dispatcher.dispatch(event)
    """

    def __init__(self, event_handler: "WappaEventHandler"):
        """
        Initialize with the event handler.

        Args:
            event_handler: WappaEventHandler instance to dispatch events to
        """
        self._event_handler = event_handler
        self.logger = get_logger(__name__)

    async def dispatch(self, event: APIMessageEvent) -> dict:
        """
        Dispatch API message event to handler.

        Calls the handler's handle_api_message() method which follows
        the Template Method pattern (pre-process, process, post-process).

        Args:
            event: APIMessageEvent with full message context

        Returns:
            Dict with success status and optional error
        """
        try:
            if self._event_handler is None:
                self.logger.warning("No event handler registered for API events")
                return {"success": False, "error": "No handler registered"}

            await self._event_handler.handle_api_message(event)

            self.logger.debug(
                f"API event dispatched: {event.message_type} to {event.recipient} "
                f"(handler: {self._event_handler.__class__.__name__})"
            )

            return {"success": True}

        except Exception as e:
            self.logger.error(f"Error dispatching API event: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
