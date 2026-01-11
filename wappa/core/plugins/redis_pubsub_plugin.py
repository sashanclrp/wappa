"""
RedisPubSubPlugin - Automatic event notifications via Redis PubSub.

Channel Pattern: wappa:notify:{tenant}:{user_id}:{event_type}

Event Types:
- incoming_message: User messages received via webhook
- outgoing_message: Messages sent via API routes
- bot_reply: Messages sent by bot via self.messenger
- status_change: Delivery/read status updates
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger
from ...persistence.redis.redis_manager import RedisManager
from ..pubsub import (
    PubSubMessageHandler,
    PubSubStatusHandler,
    publish_api_notification,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder
    from ...domain.events.api_message_event import APIMessageEvent

logger = logging.getLogger(__name__)


class RedisPubSubPlugin:
    """
    Plugin for automatic Redis PubSub event notifications.

    Wraps handlers and messengers to publish real-time notifications
    automatically. Requires RedisPlugin to be configured first.

    Event Types:
        incoming_message: Webhook-received messages (PubSubMessageHandler)
        outgoing_message: API-sent messages (_post_process_api_message hook)
        bot_reply: Bot-sent messages (PubSubMessengerWrapper)
        status_change: Status updates (PubSubStatusHandler)

    Usage:
        from wappa.core.plugins import RedisPubSubPlugin

        app = (WappaBuilder()
               .with_redis_cache("redis://localhost:6379")
               .add_plugin(RedisPubSubPlugin())
               .build())

    Subscription Examples:
        # All events for a user
        PSUBSCRIBE wappa:notify:mimeia:5511999887766:*

        # All bot replies for a tenant
        PSUBSCRIBE wappa:notify:mimeia:*:bot_reply
    """

    def __init__(
        self,
        *,
        publish_incoming: bool = True,
        publish_outgoing: bool = True,
        publish_bot_replies: bool = True,
        publish_status: bool = True,
    ):
        """
        Initialize Redis PubSub plugin.

        Args:
            publish_incoming: Publish incoming_message for webhook messages
            publish_outgoing: Publish outgoing_message for API-sent messages
            publish_bot_replies: Publish bot_reply for self.messenger sends
            publish_status: Publish status_change for delivery/read updates
        """
        self.publish_incoming = publish_incoming
        self.publish_outgoing = publish_outgoing
        self.publish_bot_replies = publish_bot_replies
        self.publish_status = publish_status

        # Track original handlers for restoration
        self._original_message_handler = None
        self._original_status_handler = None
        self._original_post_process_api = None

    def configure(self, builder: WappaBuilder) -> None:
        """Register startup and shutdown hooks with the builder."""
        builder.add_startup_hook(self._startup_hook, priority=22)
        builder.add_shutdown_hook(self._shutdown_hook, priority=22)
        get_app_logger().debug("RedisPubSubPlugin configured")

    async def startup(self, app: FastAPI) -> None:
        """Plugin startup method required by WappaPlugin protocol."""
        await self._startup_hook(app)

    async def shutdown(self, app: FastAPI) -> None:
        """Plugin shutdown method required by WappaPlugin protocol."""
        await self._shutdown_hook(app)

    async def _startup_hook(self, app: FastAPI) -> None:
        """Inject PubSub-publishing handlers and hooks."""
        app_logger = get_app_logger()
        app_logger.info("=== REDIS PUBSUB INITIALIZATION ===")

        if not RedisManager.is_initialized():
            raise RuntimeError(
                "RedisPubSubPlugin requires Redis. Add RedisPlugin first."
            )

        # Get event handler from API dispatcher
        api_dispatcher = getattr(app.state, "api_event_dispatcher", None)
        if not api_dispatcher or not hasattr(api_dispatcher, "_event_handler"):
            app_logger.warning("API event dispatcher not found. PubSub inactive.")
            return

        event_handler = api_dispatcher._event_handler
        if not event_handler:
            app_logger.warning("No event handler registered. Skipping PubSub setup.")
            return

        # Store original handlers
        self._original_message_handler = event_handler._default_message_handler
        self._original_status_handler = event_handler._default_status_handler
        self._original_post_process_api = event_handler._post_process_api_message

        handlers_wrapped = []

        # Wrap incoming message handler
        if self.publish_incoming:
            event_handler._default_message_handler = PubSubMessageHandler(
                inner_handler=self._original_message_handler,
            )
            handlers_wrapped.append("incoming_message")

        # Wrap status handler
        if self.publish_status:
            event_handler._default_status_handler = PubSubStatusHandler(
                inner_handler=self._original_status_handler,
            )
            handlers_wrapped.append("status_change")

        # Hook API events via _post_process_api_message
        if self.publish_outgoing:
            original = self._original_post_process_api

            async def wrapped_post_process(event: APIMessageEvent) -> None:
                await original(event)
                await publish_api_notification(event)

            event_handler._post_process_api_message = wrapped_post_process
            handlers_wrapped.append("outgoing_message")

        # Set flag for messenger wrapping (handled in webhook_controller)
        if self.publish_bot_replies:
            app.state.pubsub_wrap_messenger = True
            handlers_wrapped.append("bot_reply")

        # Store plugin reference
        app.state.redis_pubsub_plugin = self
        app_logger.info(f"RedisPubSubPlugin started: {', '.join(handlers_wrapped)}")

    async def _shutdown_hook(self, app: FastAPI) -> None:
        """Clean up references."""
        if hasattr(app.state, "redis_pubsub_plugin"):
            del app.state.redis_pubsub_plugin
        if hasattr(app.state, "pubsub_wrap_messenger"):
            del app.state.pubsub_wrap_messenger
        get_app_logger().info("RedisPubSubPlugin shutdown completed")

    async def get_health_status(self, app: FastAPI) -> dict[str, Any]:
        """Get plugin health status for monitoring."""
        return {
            "plugin": "RedisPubSubPlugin",
            "healthy": RedisManager.is_initialized(),
            "config": {
                "publish_incoming": self.publish_incoming,
                "publish_outgoing": self.publish_outgoing,
                "publish_bot_replies": self.publish_bot_replies,
                "publish_status": self.publish_status,
            },
            "handlers_wrapped": {
                "message_handler": self._original_message_handler is not None,
                "status_handler": self._original_status_handler is not None,
                "api_post_process": self._original_post_process_api is not None,
                "messenger_wrapper": getattr(app.state, "pubsub_wrap_messenger", False),
            },
        }

    def get_channel_pattern(
        self, tenant: str, user_id: str = "*", event_type: str = "*"
    ) -> str:
        """Build channel pattern for subscriptions."""
        from ...persistence.redis.redis_handler.utils.key_factory import KeyFactory

        return KeyFactory().channel_pattern(tenant, user_id, event_type)
