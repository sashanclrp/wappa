"""External webhook event lane of ``WappaEventHandler``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._state import _HandlerState

if TYPE_CHECKING:
    from wappa.domain.events.external_event import ExternalEvent


class _ExternalLane(_HandlerState):
    """External webhook event lane of ``WappaEventHandler``."""

    # =========== EXTERNAL WEBHOOK EVENT HANDLING ===========

    async def handle_external_event(self, event: ExternalEvent) -> None:
        """
        Handle external webhook events using Template Method pattern.

        This method provides a structured flow for events from external
        providers (MercadoPago, Stripe, CRM systems, etc.):
        1. Pre-processing: Framework logging
        2. User processing: Custom business logic (implemented in process_external_event)
        3. Post-processing: Framework cleanup

        DO NOT OVERRIDE - implement process_external_event() instead.

        Args:
            event: ExternalEvent from the external webhook processor
        """
        await self._pre_process_external_event(event)
        await self.process_external_event(event)
        await self._post_process_external_event(event)

    async def process_external_event(self, event: ExternalEvent) -> None:
        """
        Process external webhook event with custom business logic.

        Optional method - override to handle payment notifications, CRM updates,
        subscription events, or any External Webhook Source event.

        ``self.db`` and ``self.db_read`` are available when configured. An
        external webhook context resolver may also bind ``self.inbox_id``,
        ``self.user_id``, ``self.messenger``, and ``self.cache_factory``.

        Default: no-op (does nothing unless overridden).

        Args:
            event: ExternalEvent with source, event_type, payload, and full context

        Example:
            async def process_external_event(self, event: ExternalEvent) -> None:
                if event.source == "mercadopago" and event.event_type == "payment.approved":
                    if self.cache_factory:
                        cache = self.cache_factory.create_user_cache()
                        await cache.update({"subscription_status": "active"})
                    if self.messenger:
                        await self.messenger.send_text(
                            text="Payment confirmed!",
                            recipient=self.user_id,
                        )
        """
        _ = event
        return None

    async def _pre_process_external_event(self, event: ExternalEvent) -> None:
        """Pre-processing hook for external events. Override to customize."""
        self.logger.debug(
            f"External event received: {event.source}/{event.event_type} "
            f"(webhook_id={event.webhook_id}, inbox={self.inbox_id}, "
            f"user={self.user_id})"
        )

    async def _post_process_external_event(self, event: ExternalEvent) -> None:
        """Post-processing hook for external events. Override to customize."""
        _ = event
        return None
