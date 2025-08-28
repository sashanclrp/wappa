"""
Event dispatcher for routing webhooks to event handlers.

Simplified version of the SimpleEventDispatcher focused on the core webhook routing pattern.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from wappa.core.logging.logger import get_logger

if TYPE_CHECKING:
    from wappa.webhooks import (
        ErrorWebhook,
        IncomingMessageWebhook,
        StatusWebhook,
        UniversalWebhook,
    )

    from .event_handler import WappaEventHandler


class WappaEventDispatcher:
    """
    Event dispatcher service for Wappa applications.

    Routes universal webhooks to the user's event handler with clean dispatch logic.
    This is the core abstraction that developers interact with - they implement
    WappaEventHandler methods and this dispatcher routes webhooks to them.
    """

    def __init__(self, event_handler: "WappaEventHandler"):
        """
        Initialize the event dispatcher with the user's event handler.

        Args:
            event_handler: WappaEventHandler instance with injected dependencies
        """
        # Use context-aware logger that automatically gets tenant/user context
        self.logger = get_logger(__name__)
        self._event_handler = event_handler

        self.logger.info(
            f"WappaEventDispatcher initialized with {event_handler.__class__.__name__}"
        )

    async def dispatch_universal_webhook(
        self,
        universal_webhook: "UniversalWebhook",
        tenant_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Dispatch Universal Webhook to the appropriate handler method.

        Args:
            universal_webhook: Universal webhook interface instance
            tenant_id: Optional tenant ID for context
            **kwargs: Additional dispatch parameters

        Returns:
            Dictionary with dispatch results
        """
        dispatch_start = datetime.utcnow()

        try:
            # Log webhook type and basic info
            webhook_type = type(universal_webhook).__name__
            platform_or_provider = getattr(
                universal_webhook,
                "platform",
                getattr(universal_webhook, "provider", "unknown"),
            )
            if hasattr(platform_or_provider, "value"):
                platform_or_provider = platform_or_provider.value

            # Use emoji and shorter format for webhook processing
            webhook_emoji = {
                "IncomingMessageWebhook": "💬",
                "StatusWebhook": "📊",
                "ErrorWebhook": "🚨",
            }.get(webhook_type, "📨")

            self.logger.info(
                f"{webhook_emoji} {webhook_type.replace('Webhook', '')} from {platform_or_provider}"
            )

            # Route to appropriate handler method
            result = None
            if universal_webhook.__class__.__name__ == "IncomingMessageWebhook":
                result = await self._handle_message_webhook(universal_webhook)
            elif universal_webhook.__class__.__name__ == "StatusWebhook":
                result = await self._handle_status_webhook(universal_webhook)
            elif universal_webhook.__class__.__name__ == "ErrorWebhook":
                result = await self._handle_error_webhook(universal_webhook)
            else:
                return {
                    "success": False,
                    "error": f"Unknown webhook type: {webhook_type}",
                    "processed_at": datetime.utcnow().isoformat(),
                }

            # Add timing information if result exists
            if result:
                dispatch_end = datetime.utcnow()
                result["dispatch_time"] = (
                    dispatch_end - dispatch_start
                ).total_seconds()
                result["processed_at"] = dispatch_end.isoformat()
                self.logger.info(f"⚡ Processed in {result['dispatch_time']:.3f}s")

            return result

        except Exception as e:
            self.logger.error(f"Error processing webhook: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "processed_at": datetime.utcnow().isoformat(),
            }

    async def _handle_message_webhook(
        self, webhook: "IncomingMessageWebhook"
    ) -> dict[str, Any]:
        """
        Handle incoming message webhook by routing to user's handler.

        Args:
            webhook: Incoming message webhook

        Returns:
            Dictionary with handling results
        """
        try:
            # Enhanced message routing log
            handler_name = self._event_handler.__class__.__name__.replace(
                "EventHandler", ""
            )
            msg_type = webhook.get_message_type_name()

            self.logger.info(
                f"💬 {msg_type} message → {handler_name} (from: {webhook.user.user_id})"
            )

            # Call user's handle_message method
            await self._event_handler.handle_message(webhook)

            return {
                "success": True,
                "action": "message_processed",
                "dispatcher": "WappaEventDispatcher",
                "handler": self._event_handler.__class__.__name__,
            }

        except Exception as e:
            self.logger.error(f"Error in message handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
                "dispatcher": "WappaEventDispatcher",
                "handler": self._event_handler.__class__.__name__,
            }

    async def _handle_status_webhook(self, webhook: "StatusWebhook") -> dict[str, Any]:
        """
        Handle status webhook by routing to user's handler.

        Args:
            webhook: Status webhook

        Returns:
            Dictionary with handling results
        """
        try:
            # Enhanced status logging without message ID
            status_emoji = {
                "sent": "📤",
                "delivered": "✅",
                "read": "👁️",
                "failed": "❌",
            }.get(webhook.status.value, "📋")

            self.logger.info(
                f"{status_emoji} Status Update: {webhook.status.value.upper()} "
                f"(recipient: {webhook.recipient_id})"
            )

            # Call user's handle_status method (optional)
            await self._event_handler.handle_status(webhook)

            return {
                "success": True,
                "action": "status_processed",
                "message_id": webhook.message_id,
                "status": webhook.status.value,
                "recipient": webhook.recipient_id,
            }

        except Exception as e:
            self.logger.error(f"Error in status handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
            }

    async def _handle_error_webhook(self, webhook: "ErrorWebhook") -> dict[str, Any]:
        """
        Handle error webhook by routing to user's handler.

        Args:
            webhook: Error webhook

        Returns:
            Dictionary with handling results
        """
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"Platform error webhook: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title}"
            )

            # Call user's handle_error method (optional)
            await self._event_handler.handle_error(webhook)

            return {
                "success": True,
                "action": "error_processed",
                "error_count": error_count,
                "primary_error_code": primary_error.error_code,
                "primary_error_title": primary_error.error_title,
            }

        except Exception as e:
            self.logger.error(f"Error in error handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
            }
