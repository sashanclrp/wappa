"""
PubSub-publishing wrappers for event handlers.

Extends DefaultMessageHandler and DefaultStatusHandler to add
Redis PubSub notifications without modifying existing behavior.

Event Types:
- incoming_message: User messages received via webhook
- outgoing_message: Messages sent via API routes
- bot_reply: Messages sent by bot via self.messenger
- status_change: Delivery/read status updates
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.pubsub_interface import PubSubEventType
from ...persistence.redis.redis_handler.pubsub import RedisPubSubPublisher
from ...webhooks import IncomingMessageWebhook, StatusWebhook
from ..events.default_handlers import (
    DefaultMessageHandler,
    DefaultStatusHandler,
    LogLevel,
    MessageLogStrategy,
    StatusLogStrategy,
)

if TYPE_CHECKING:
    from ...domain.events.api_message_event import APIMessageEvent

logger = logging.getLogger(__name__)


async def publish_notification(
    event_type: PubSubEventType,
    tenant: str,
    user_id: str,
    platform: str,
    data: dict[str, Any],
) -> int:
    """
    Publish notification via PubSub.

    Failures are logged but don't propagate - notifications should never
    break the main processing flow.

    Returns:
        Number of subscribers that received the message (0 on failure)
    """
    try:
        publisher = RedisPubSubPublisher(
            tenant=tenant,
            user_id=user_id,
            platform=platform,
        )
        subscribers = await publisher.publish(event_type, data)
        if subscribers > 0:
            logger.debug(f"PubSub: {event_type} -> {subscribers} subscriber(s)")
        return subscribers
    except Exception as e:
        logger.warning(f"Failed to publish {event_type} notification: {e}")
        return 0


async def publish_api_notification(event: APIMessageEvent) -> int:
    """
    Publish API message notification via PubSub.

    Called after API-sent messages (POST /api/messages/*) to notify
    subscribers of outgoing messages.

    Returns:
        Number of subscribers that received the message
    """
    return await publish_notification(
        event_type="outgoing_message",
        tenant=event.tenant_id or "unknown",
        user_id=event.recipient,
        platform="whatsapp",
        data={
            "message_id": event.message_id or "",
            "message_type": event.message_type,
            "success": event.response_success,
        },
    )


class PubSubMessageHandler(DefaultMessageHandler):
    """Extends DefaultMessageHandler to publish incoming_message notifications."""

    def __init__(
        self,
        inner_handler: DefaultMessageHandler | None = None,
        log_strategy: MessageLogStrategy = MessageLogStrategy.SUMMARIZED,
        log_level: LogLevel = LogLevel.INFO,
        content_preview_length: int = 100,
        mask_sensitive_data: bool = True,
    ):
        if inner_handler:
            super().__init__(
                log_strategy=inner_handler.log_strategy,
                log_level=inner_handler.log_level,
                content_preview_length=inner_handler.content_preview_length,
                mask_sensitive_data=inner_handler.mask_sensitive_data,
            )
            self._stats = inner_handler._stats.copy()
        else:
            super().__init__(
                log_strategy=log_strategy,
                log_level=log_level,
                content_preview_length=content_preview_length,
                mask_sensitive_data=mask_sensitive_data,
            )

    async def log_incoming_message(self, webhook: IncomingMessageWebhook) -> None:
        """Log message and publish incoming_message notification."""
        await super().log_incoming_message(webhook)

        tenant = webhook.tenant.get_tenant_key() if webhook.tenant else "unknown"
        user_id = webhook.user.user_id if webhook.user else "unknown"
        platform = webhook.platform.value if webhook.platform else "whatsapp"

        await publish_notification(
            event_type="incoming_message",
            tenant=tenant,
            user_id=user_id,
            platform=platform,
            data={
                "message_id": webhook.message.message_id if webhook.message else "",
                "message_type": webhook.get_message_type_name(),
            },
        )


class PubSubStatusHandler(DefaultStatusHandler):
    """Extends DefaultStatusHandler to publish status_change notifications."""

    def __init__(
        self,
        inner_handler: DefaultStatusHandler | None = None,
        log_strategy: StatusLogStrategy = StatusLogStrategy.IMPORTANT_ONLY,
        log_level: LogLevel = LogLevel.INFO,
    ):
        if inner_handler:
            super().__init__(
                log_strategy=inner_handler.log_strategy,
                log_level=inner_handler.log_level,
            )
            self._stats = inner_handler._stats.copy()
        else:
            super().__init__(
                log_strategy=log_strategy,
                log_level=log_level,
            )

    async def handle_status(self, webhook: StatusWebhook) -> dict[str, Any]:
        """Handle status and publish status_change notification."""
        result = await super().handle_status(webhook)

        tenant = webhook.tenant.get_tenant_key() if webhook.tenant else "unknown"
        platform = webhook.platform.value if webhook.platform else "whatsapp"

        await publish_notification(
            event_type="status_change",
            tenant=tenant,
            user_id=webhook.recipient_id,
            platform=platform,
            data={
                "message_id": webhook.message_id,
                "status": webhook.status.value,
            },
        )

        return result
