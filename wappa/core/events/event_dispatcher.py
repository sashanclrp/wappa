from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from wappa.core.logging.logger import get_logger
from wappa.webhooks import (
    ErrorWebhook,
    IncomingMessageWebhook,
    StatusWebhook,
    SystemWebhook,
)

if TYPE_CHECKING:
    from wappa.webhooks import UniversalWebhook

    from .event_handler import WappaEventHandler


_WEBHOOK_EMOJI = {
    "IncomingMessageWebhook": "💬",
    "StatusWebhook": "📊",
    "ErrorWebhook": "🚨",
    "SystemWebhook": "⚙️",
}

_STATUS_EMOJI = {
    "sent": "📤",
    "delivered": "✅",
    "read": "👁️",
    "failed": "❌",
}


class WappaEventDispatcher:
    # Routes universal webhooks to the user's event handler.

    def __init__(self, event_handler: "WappaEventHandler"):
        self.logger = get_logger(__name__)
        self._event_handler = event_handler

        self.logger.info(
            f"WappaEventDispatcher initialized with {event_handler.__class__.__name__}"
        )

    @property
    def event_handler(self) -> "WappaEventHandler":
        return self._event_handler

    async def dispatch_universal_webhook(
        self,
        universal_webhook: "UniversalWebhook",
        tenant_id: str | None = None,
        request_handler: "WappaEventHandler | None" = None,
        **kwargs,
    ) -> dict[str, Any]:
        dispatch_start = datetime.now(UTC)
        handler = request_handler or self._event_handler

        try:
            webhook_type = type(universal_webhook).__name__
            platform_or_provider = getattr(
                universal_webhook,
                "platform",
                getattr(universal_webhook, "provider", "unknown"),
            )
            if hasattr(platform_or_provider, "value"):
                platform_or_provider = platform_or_provider.value

            emoji = _WEBHOOK_EMOJI.get(webhook_type, "📨")
            self.logger.info(
                f"{emoji} {webhook_type.replace('Webhook', '')} from {platform_or_provider}"
            )

            match universal_webhook:
                case IncomingMessageWebhook():
                    result = await self._handle_message_webhook(universal_webhook, handler)
                case StatusWebhook():
                    result = await self._handle_status_webhook(universal_webhook, handler)
                case ErrorWebhook():
                    result = await self._handle_error_webhook(universal_webhook, handler)
                case SystemWebhook():
                    result = await self._handle_system_webhook(universal_webhook, handler)
                case _:
                    return {
                        "success": False,
                        "error": f"Unknown webhook type: {webhook_type}",
                        "processed_at": datetime.now(UTC).isoformat(),
                    }

            if result:
                dispatch_end = datetime.now(UTC)
                result["dispatch_time"] = (dispatch_end - dispatch_start).total_seconds()
                result["processed_at"] = dispatch_end.isoformat()
                self.logger.info(f"⚡ Processed in {result['dispatch_time']:.3f}s")

            return result

        except Exception as e:
            self.logger.error(f"Error processing webhook: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "processed_at": datetime.now(UTC).isoformat(),
            }

    async def _handle_message_webhook(
        self,
        webhook: "IncomingMessageWebhook",
        handler: "WappaEventHandler",
    ) -> dict[str, Any]:
        try:
            handler_name = handler.__class__.__name__.replace("EventHandler", "")
            self.logger.info(
                f"💬 {webhook.get_message_type_name()} message → {handler_name} "
                f"(from: {webhook.user.user_id}, tenant: {handler.tenant_id})"
            )

            await handler.handle_message(webhook)

            return {
                "success": True,
                "action": "message_processed",
                "dispatcher": "WappaEventDispatcher",
                "handler": handler.__class__.__name__,
                "tenant_id": handler.tenant_id,
                "user_id": handler.user_id,
            }

        except Exception as e:
            self.logger.error(f"Error in message handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
                "dispatcher": "WappaEventDispatcher",
                "handler": handler.__class__.__name__,
            }

    async def _handle_status_webhook(
        self,
        webhook: "StatusWebhook",
        handler: "WappaEventHandler",
    ) -> dict[str, Any]:
        try:
            status_value = webhook.status.value
            emoji = _STATUS_EMOJI.get(status_value, "📋")

            self.logger.info(
                f"{emoji} Status Update: {status_value.upper()} "
                f"(recipient: {webhook.recipient_id}, tenant: {handler.tenant_id})"
            )

            await handler.handle_status(webhook)

            return {
                "success": True,
                "action": "status_processed",
                "message_id": webhook.message_id,
                "status": status_value,
                "recipient": webhook.recipient_id,
                "tenant_id": handler.tenant_id,
            }

        except Exception as e:
            self.logger.error(f"Error in status handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
            }

    async def _handle_error_webhook(
        self,
        webhook: "ErrorWebhook",
        handler: "WappaEventHandler",
    ) -> dict[str, Any]:
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"Platform error webhook: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title} "
                f"(tenant: {handler.tenant_id})"
            )

            await handler.handle_error(webhook)

            return {
                "success": True,
                "action": "error_processed",
                "error_count": error_count,
                "primary_error_code": primary_error.error_code,
                "primary_error_title": primary_error.error_title,
                "tenant_id": handler.tenant_id,
            }

        except Exception as e:
            self.logger.error(f"Error in error handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
            }

    async def _handle_system_webhook(
        self,
        webhook: "SystemWebhook",
        handler: "WappaEventHandler",
    ) -> dict[str, Any]:
        try:
            self.logger.info(
                f"⚙️ System event: {webhook.system_event_type.value} "
                f"(tenant: {handler.tenant_id})"
            )

            await handler.handle_system(webhook)

            return {
                "success": True,
                "action": "system_event_processed",
                "system_event_type": webhook.system_event_type.value,
                "tenant_id": handler.tenant_id,
            }

        except Exception as e:
            self.logger.error(f"Error in system handler: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "action": "handler_error",
            }
