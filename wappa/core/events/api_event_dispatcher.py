"""
API event dispatcher for outgoing message events.

Follows Single Responsibility Principle:
- Only handles dispatching API events to handlers
- Does not handle webhook events (that's WappaEventDispatcher)
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from wappa.core.logging.logger import get_logger
from wappa.core.sse.context import classify_meta_identifier, sse_event_scope
from wappa.domain.events.api_message_event import APIMessageEvent

if TYPE_CHECKING:
    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.core.events.event_handler import WappaEventHandler


class APIEventDispatcher:
    """
    Dispatches API message events to the registered event handler.

    This dispatcher follows the Observer pattern - it observes API calls
    and notifies the registered WappaEventHandler when messages are sent.

    The dispatcher creates a context-bound handler clone for each dispatch,
    injecting database session factories when PostgresDatabasePlugin is configured.
    This ensures process_api_message() has access to self.db just like webhook handlers.

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
        await dispatcher.dispatch(event, request)  # Pass request for DB access
    """

    def __init__(self, event_handler: "WappaEventHandler"):
        """
        Initialize with the event handler.

        Args:
            event_handler: WappaEventHandler instance to dispatch events to
        """
        self._event_handler = event_handler
        self.logger = get_logger(__name__)

    async def dispatch(
        self,
        event: APIMessageEvent,
        request: "Request | None" = None,
    ) -> dict:
        """
        Dispatch API message event to handler with full dependency injection.

        Creates a context-bound handler clone with database session factories
        injected (when PostgresDatabasePlugin is configured), ensuring
        process_api_message() has access to self.db.

        Args:
            event: APIMessageEvent with full message context
            request: FastAPI Request object for accessing app.state (optional for
                     backwards compatibility, but required for DB access)

        Returns:
            Dict with success status and optional error
        """
        try:
            if self._event_handler is None:
                self.logger.warning("No event handler registered for API events")
                return {"success": False, "error": "No handler registered"}

            # Create context-bound handler clone with dependencies injected
            request_handler = self._create_api_request_handler(event, request)

            # Resolve SSE identity from the event: if `user_id` is a BSUID
            # shape, surface it; otherwise treat `recipient` as the wa_id and
            # fall back to `user_id` for the canonical envelope slot.
            canonical_user_id = event.user_id or event.recipient
            bsuid, phone = classify_meta_identifier(event.recipient)
            if bsuid is None:
                bsuid, _ = classify_meta_identifier(canonical_user_id)

            async with sse_event_scope(
                tenant_id=event.tenant_id or "unknown",
                user_id=canonical_user_id,
                bsuid=bsuid,
                phone_number=phone,
                platform=event.platform or "whatsapp",
            ):
                await request_handler.handle_api_message(event)

            self.logger.debug(
                f"API event dispatched: {event.message_type} to {event.recipient} "
                f"(handler: {request_handler.__class__.__name__}, "
                f"db_available: {request_handler.db is not None})"
            )

            return {"success": True}

        except Exception as e:
            self.logger.error(f"Error dispatching API event: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _create_api_request_handler(
        self,
        event: APIMessageEvent,
        request: "Request | None",
    ) -> "WappaEventHandler":
        """
        Create a context-bound handler clone for API event processing.

        Similar to WebhookController._create_request_handler(), this method
        creates a handler clone with database session factories injected.

        For API events, messenger and cache_factory are set to None since
        API routes have their own messenger dependency injection.

        Args:
            event: APIMessageEvent containing tenant_id and recipient
            request: FastAPI Request for accessing app.state

        Returns:
            Context-bound WappaEventHandler instance
        """
        # Get database session factories if PostgresDatabasePlugin is registered
        db: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None
        db_read: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None

        if request is not None:
            session_manager = getattr(
                request.app.state, "postgres_session_manager", None
            )
            if session_manager:
                db = session_manager.get_session
                db_read = session_manager.get_read_session

        self.logger.debug(
            f"API handler context: tenant={event.tenant_id}, db_available={db is not None}"
        )

        # Clone handler with context for this API event.
        # Prefer the caller-supplied canonical user_id over recipient so
        # self.user_id inside process_api_message() is the domain identifier
        # for state/cache lookups, not the Meta transport value. Defaults to
        # recipient when the caller did not provide a distinct user_id.
        return self._event_handler.with_context(
            tenant_id=event.tenant_id,
            user_id=event.user_id or event.recipient,
            messenger=None,  # API routes use their own messenger dependency
            cache_factory=None,  # API routes can inject cache if needed
            db=db,
            db_read=db_read,
        )
