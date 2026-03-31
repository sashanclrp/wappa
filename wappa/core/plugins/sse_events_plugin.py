"""SSEEventsPlugin - real-time full-payload event streaming over SSE."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...api.routes.sse import router as sse_router
from ...core.logging.logger import get_app_logger
from ...core.sse import (
    SUPPORTED_SSE_EVENT_TYPES,
    SSEErrorHandler,
    SSEEventHub,
    SSEMessageHandler,
    SSEStatusHandler,
    publish_api_sse_event,
    register_sse_event_type,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder
    from ...domain.events.api_message_event import APIMessageEvent

logger = logging.getLogger(__name__)


class SSEEventsPlugin:
    """Plugin that streams incoming/outgoing/status/error events via SSE."""

    def __init__(
        self,
        *,
        publish_incoming: bool = True,
        publish_outgoing_api: bool = True,
        publish_bot_replies: bool = True,
        publish_status: bool = True,
        publish_webhook_errors: bool = True,
        queue_size: int = 200,
        custom_event_types: set[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.publish_incoming = publish_incoming
        self.publish_outgoing_api = publish_outgoing_api
        self.publish_bot_replies = publish_bot_replies
        self.publish_status = publish_status
        self.publish_webhook_errors = publish_webhook_errors
        self.queue_size = queue_size
        self.custom_event_types = custom_event_types or set()
        self.metadata = metadata

        self._original_message_handler = None
        self._original_status_handler = None
        self._original_error_handler = None
        self._api_post_process_hook = None

        # SSE handler references for runtime metadata updates
        self._sse_message_handler: SSEMessageHandler | None = None
        self._sse_status_handler: SSEStatusHandler | None = None
        self._sse_error_handler: SSEErrorHandler | None = None

    def update_metadata(self, **kwargs: Any) -> None:
        """Update metadata on all active SSE handlers."""
        if self.metadata is None:
            self.metadata = {}
        self.metadata.update(kwargs)
        if self._sse_message_handler:
            self._sse_message_handler.update_metadata(**kwargs)
        if self._sse_status_handler:
            self._sse_status_handler.update_metadata(**kwargs)
        if self._sse_error_handler:
            self._sse_error_handler.update_metadata(**kwargs)

    def configure(self, builder: WappaBuilder) -> None:
        """Register SSE routes and lifecycle hooks."""
        builder.add_router(sse_router)
        builder.add_startup_hook(self._startup_hook, priority=24)
        builder.add_shutdown_hook(self._shutdown_hook, priority=24)
        get_app_logger().debug("SSEEventsPlugin configured")

    async def startup(self, app: FastAPI) -> None:
        """Plugin startup method required by WappaPlugin protocol."""
        await self._startup_hook(app)

    async def shutdown(self, app: FastAPI) -> None:
        """Plugin shutdown method required by WappaPlugin protocol."""
        await self._shutdown_hook(app)

    async def _startup_hook(self, app: FastAPI) -> None:
        """Inject SSE wrappers and initialize event hub."""
        app_logger = get_app_logger()
        app_logger.info("=== SSE PLUGIN INITIALIZATION ===")

        event_hub = SSEEventHub(queue_size=self.queue_size)
        app.state.sse_event_hub = event_hub

        for event_type in self.custom_event_types:
            register_sse_event_type(event_type)
        if self.custom_event_types:
            app_logger.info(
                "SSE custom event types registered: %s",
                ", ".join(sorted(self.custom_event_types)),
            )

        api_dispatcher = getattr(app.state, "api_event_dispatcher", None)
        if not api_dispatcher or not hasattr(api_dispatcher, "_event_handler"):
            app_logger.warning("API event dispatcher not found. SSE wrappers inactive.")
            app.state.sse_events_plugin = self
            return

        event_handler = api_dispatcher._event_handler
        if not event_handler:
            app_logger.warning("No event handler registered. SSE wrappers inactive.")
            app.state.sse_events_plugin = self
            return

        self._original_message_handler = event_handler._default_message_handler
        self._original_status_handler = event_handler._default_status_handler
        self._original_error_handler = event_handler._default_error_handler

        handlers_wrapped: list[str] = []

        if self.publish_incoming:
            self._sse_message_handler = SSEMessageHandler(
                event_hub=event_hub,
                inner_handler=self._original_message_handler,
                metadata=self.metadata,
            )
            event_handler._default_message_handler = self._sse_message_handler
            handlers_wrapped.append("incoming_message")

        if self.publish_status:
            self._sse_status_handler = SSEStatusHandler(
                event_hub=event_hub,
                inner_handler=self._original_status_handler,
                metadata=self.metadata,
            )
            event_handler._default_status_handler = self._sse_status_handler
            handlers_wrapped.append("status_change")

        if self.publish_webhook_errors:
            self._sse_error_handler = SSEErrorHandler(
                event_hub=event_hub,
                inner_handler=self._original_error_handler,
                metadata=self.metadata,
            )
            event_handler._default_error_handler = self._sse_error_handler
            handlers_wrapped.append("webhook_error")

        if self.publish_outgoing_api:
            meta = self.metadata

            async def _sse_api_hook(event: APIMessageEvent) -> None:
                await publish_api_sse_event(event_hub, event, metadata=meta)

            self._api_post_process_hook = _sse_api_hook
            event_handler.add_api_post_process_hook(_sse_api_hook)
            handlers_wrapped.append("outgoing_api_message")

        if self.publish_bot_replies:
            app.state.sse_wrap_messenger = True
            handlers_wrapped.append("outgoing_bot_message")

        app.state.sse_events_plugin = self

        if handlers_wrapped:
            app_logger.info("SSEEventsPlugin started: %s", ", ".join(handlers_wrapped))
        else:
            app_logger.info("SSEEventsPlugin started: router only")

    async def _shutdown_hook(self, app: FastAPI) -> None:
        """Restore handler state and close event hub."""
        SUPPORTED_SSE_EVENT_TYPES.difference_update(self.custom_event_types)

        api_dispatcher = getattr(app.state, "api_event_dispatcher", None)
        event_handler = getattr(api_dispatcher, "_event_handler", None)

        if event_handler:
            if self._original_message_handler is not None:
                event_handler._default_message_handler = self._original_message_handler
            if self._original_status_handler is not None:
                event_handler._default_status_handler = self._original_status_handler
            if self._original_error_handler is not None:
                event_handler._default_error_handler = self._original_error_handler
            if self._api_post_process_hook is not None:
                event_handler.remove_api_post_process_hook(self._api_post_process_hook)
                self._api_post_process_hook = None

        event_hub = getattr(app.state, "sse_event_hub", None)
        if isinstance(event_hub, SSEEventHub):
            await event_hub.shutdown()

        if hasattr(app.state, "sse_events_plugin"):
            del app.state.sse_events_plugin
        if hasattr(app.state, "sse_wrap_messenger"):
            del app.state.sse_wrap_messenger
        if hasattr(app.state, "sse_event_hub"):
            del app.state.sse_event_hub

        get_app_logger().info("SSEEventsPlugin shutdown completed")

    async def get_health_status(self, app: FastAPI) -> dict[str, Any]:
        """Get plugin health status for monitoring."""
        event_hub = getattr(app.state, "sse_event_hub", None)
        hub_stats: dict[str, int] = {}
        if isinstance(event_hub, SSEEventHub):
            hub_stats = event_hub.get_stats()

        return {
            "plugin": "SSEEventsPlugin",
            "healthy": isinstance(event_hub, SSEEventHub),
            "config": {
                "publish_incoming": self.publish_incoming,
                "publish_outgoing_api": self.publish_outgoing_api,
                "publish_bot_replies": self.publish_bot_replies,
                "publish_status": self.publish_status,
                "publish_webhook_errors": self.publish_webhook_errors,
                "queue_size": self.queue_size,
            },
            "handlers_wrapped": {
                "message_handler": self._original_message_handler is not None,
                "status_handler": self._original_status_handler is not None,
                "error_handler": self._original_error_handler is not None,
                "api_post_process": self._api_post_process_hook is not None,
                "messenger_wrapper": getattr(app.state, "sse_wrap_messenger", False),
            },
            "hub": hub_stats,
        }
