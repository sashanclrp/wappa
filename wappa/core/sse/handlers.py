"""SSE-publishing wrappers for event handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final, Literal

from ...webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook
from ..events.default_handlers import (
    DefaultErrorHandler,
    DefaultMessageHandler,
    DefaultStatusHandler,
    ErrorLogStrategy,
    LogLevel,
    MessageLogStrategy,
    StatusLogStrategy,
)
from .event_hub import SSEEventHub

if TYPE_CHECKING:
    from ...domain.events.api_message_event import APIMessageEvent

logger = logging.getLogger(__name__)

SSEEventType = Literal[
    "incoming_message",
    "outgoing_api_message",
    "outgoing_bot_message",
    "status_change",
    "webhook_error",
]

_BUILTIN_SSE_EVENT_TYPES: Final[set[str]] = {
    "incoming_message",
    "outgoing_api_message",
    "outgoing_bot_message",
    "status_change",
    "webhook_error",
}

SUPPORTED_SSE_EVENT_TYPES: set[str] = set(_BUILTIN_SSE_EVENT_TYPES)


def register_sse_event_type(event_type: str) -> None:
    """Register a custom SSE event type for app-level events."""
    SUPPORTED_SSE_EVENT_TYPES.add(event_type)


def _normalized_webhook_payload(
    webhook: IncomingMessageWebhook | StatusWebhook | ErrorWebhook,
) -> dict[str, Any]:
    """Build normalized webhook payload for SSE messages.

    For IncomingMessageWebhook the message field is enriched via
    ``to_universal_dict()`` so that abstract-property content
    (text_content, media_id, selected_option_id, …) is included.
    Plain ``model_dump()`` only captures Pydantic fields (e.g.
    ``processed_at``) and silently drops all property-based data.
    """
    data = webhook.model_dump(mode="json", exclude_none=False)

    if isinstance(webhook, IncomingMessageWebhook):
        data["message"] = webhook.message.to_universal_dict()

    return data


async def publish_sse_event(
    event_hub: SSEEventHub | None,
    *,
    event_type: str,
    tenant_id: str,
    user_id: str,
    platform: str,
    source: str,
    payload: dict[str, Any],
) -> int:
    """Publish one event to SSE subscribers without impacting main flow."""
    if event_hub is None:
        return 0

    try:
        subscribers = await event_hub.publish(
            event_type=event_type,
            tenant_id=tenant_id,
            user_id=user_id,
            platform=platform,
            source=source,
            payload=payload,
        )
        if subscribers > 0:
            logger.debug(
                "SSE: %s delivered to %s subscriber(s)", event_type, subscribers
            )
        return subscribers
    except Exception as exc:
        logger.warning("Failed to publish SSE event %s: %s", event_type, exc)
        return 0


async def publish_api_sse_event(
    event_hub: SSEEventHub | None,
    event: APIMessageEvent,
) -> int:
    """Publish full API outgoing message context through SSE."""
    return await publish_sse_event(
        event_hub,
        event_type="outgoing_api_message",
        tenant_id=event.tenant_id or "unknown",
        user_id=event.recipient,
        platform=event.platform,
        source="api",
        payload=event.model_dump(mode="json", exclude_none=False),
    )


class SSEMessageHandler(DefaultMessageHandler):
    """Wraps default incoming-message logging and publishes SSE payloads."""

    def __init__(
        self,
        event_hub: SSEEventHub,
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

        self._event_hub = event_hub

    async def log_incoming_message(self, webhook: IncomingMessageWebhook) -> None:
        """Log incoming message then publish full webhook payload via SSE."""
        await super().log_incoming_message(webhook)

        tenant_id = webhook.tenant.get_tenant_key() if webhook.tenant else "unknown"
        user_id = webhook.user.user_id if webhook.user else "unknown"
        platform = webhook.platform.value if webhook.platform else "whatsapp"

        await publish_sse_event(
            self._event_hub,
            event_type="incoming_message",
            tenant_id=tenant_id,
            user_id=user_id,
            platform=platform,
            source="webhook",
            payload=_normalized_webhook_payload(webhook),
        )


class SSEStatusHandler(DefaultStatusHandler):
    """Wraps status logging and publishes full status payload through SSE."""

    def __init__(
        self,
        event_hub: SSEEventHub,
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

        self._event_hub = event_hub

    async def handle_status(self, webhook: StatusWebhook) -> dict[str, Any]:
        """Handle status, then publish full status webhook data."""
        result = await super().handle_status(webhook)

        tenant_id = webhook.tenant.get_tenant_key() if webhook.tenant else "unknown"
        platform = webhook.platform.value if webhook.platform else "whatsapp"
        user_id = webhook.recipient_id or "unknown"

        await publish_sse_event(
            self._event_hub,
            event_type="status_change",
            tenant_id=tenant_id,
            user_id=user_id,
            platform=platform,
            source="webhook",
            payload=_normalized_webhook_payload(webhook),
        )

        return result


class SSEErrorHandler(DefaultErrorHandler):
    """Wraps error handling and publishes full error webhook payloads."""

    def __init__(
        self,
        event_hub: SSEEventHub,
        inner_handler: DefaultErrorHandler | None = None,
        log_strategy: ErrorLogStrategy = ErrorLogStrategy.ALL,
        escalation_threshold: int = 5,
        escalation_window_minutes: int = 10,
    ):
        if inner_handler:
            super().__init__(
                log_strategy=inner_handler.log_strategy,
                escalation_threshold=inner_handler.escalation_threshold,
                escalation_window_minutes=inner_handler.escalation_window_minutes,
            )
            self._stats = inner_handler._stats.copy()
        else:
            super().__init__(
                log_strategy=log_strategy,
                escalation_threshold=escalation_threshold,
                escalation_window_minutes=escalation_window_minutes,
            )

        self._event_hub = event_hub

    async def handle_error(self, webhook: ErrorWebhook) -> dict[str, Any]:
        """Handle error and publish full webhook payload through SSE."""
        result = await super().handle_error(webhook)

        tenant_id = webhook.tenant.get_tenant_key() if webhook.tenant else "unknown"
        platform = webhook.platform.value if webhook.platform else "whatsapp"

        await publish_sse_event(
            self._event_hub,
            event_type="webhook_error",
            tenant_id=tenant_id,
            user_id="system",
            platform=platform,
            source="webhook",
            payload=_normalized_webhook_payload(webhook),
        )

        return result
