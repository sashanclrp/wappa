"""Outgoing API message lane of ``WappaEventHandler``."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from ._state import _HandlerState

if TYPE_CHECKING:
    from wappa.domain.events.api_message_event import APIMessageEvent


class _ApiLane(_HandlerState):
    """Outgoing API message lane of ``WappaEventHandler``."""

    # =========== OUTGOING API MESSAGE HANDLING ===========

    async def handle_api_message(self, event: APIMessageEvent) -> None:
        """
        Handle API-sent message events using Template Method pattern.

        This method provides a structured flow for outgoing messages sent
        via the REST API (not webhooks):
        1. Pre-processing: Framework logging
        2. User processing: Custom business logic (implemented in process_api_message)
        3. Post-processing: Framework cleanup

        DO NOT OVERRIDE - implement process_api_message() instead.

        Args:
            event: APIMessageEvent containing the outgoing message context
        """
        await self._pre_process_api_message(event)
        await self.process_api_message(event)
        await self._post_process_api_message(event)

    async def process_api_message(self, event: APIMessageEvent) -> None:
        """
        Process API-sent message event with custom business logic.

        Optional method - override to track outgoing messages, update databases,
        or trigger workflows when messages are sent via the REST API.

        This method is NOT called for webhook-received messages - those go through
        process_message(). This is specifically for messages sent via:
        - POST /api/whatsapp/messages/*
        - POST /api/whatsapp/media/*
        - POST /api/whatsapp/templates/*
        - POST /api/whatsapp/interactive/*

        Default: no-op (does nothing unless overridden).

        Database Access:
            self.db is available when PostgresDatabasePlugin is configured AND the
            API route passes the FastAPI Request to the event dispatcher. Without
            Request, self.db will be None - check before using:

            if self.db:
                async with self.db() as session:
                    # Your database operations
                    pass

        Args:
            event: APIMessageEvent with full context (request, response, inbox)

        Example:
            async def process_api_message(self, event: APIMessageEvent) -> None:
                # Check if database is available
                if not self.db:
                    self.logger.debug("Database not available for API event")
                    return

                # Log outgoing message to database
                async with self.db() as session:
                    message = Message(
                        recipient=event.recipient,
                        message_type=event.message_type,
                        message_id=event.message_id,
                        success=event.response_success,
                    )
                    session.add(message)
                    # Auto-commits on context exit

                # Trigger analytics
                if event.response_success:
                    await self.analytics.track_message_sent(event)
        """
        _ = event
        return None

    async def _pre_process_api_message(self, event: APIMessageEvent) -> None:
        """
        Pre-processing hook for API messages.

        Override to customize pre-processing behavior.
        Default: logs the API message event.
        """
        self.logger.debug(
            f"API message sent: {event.message_type} to {event.recipient} "
            f"(success={event.response_success})"
        )

    async def _post_process_api_message(self, event: APIMessageEvent) -> None:
        """Post-processing hook for API messages. Runs registered hooks."""
        for hook in self._api_post_process_hooks:
            await hook(event)

    def add_api_post_process_hook(self, hook: Callable) -> None:
        """Register a callback to run after API message post-processing."""
        self._api_post_process_hooks.append(hook)

    def remove_api_post_process_hook(self, hook: Callable) -> None:
        """Remove a previously registered post-process hook."""
        with contextlib.suppress(ValueError):
            self._api_post_process_hooks.remove(hook)
