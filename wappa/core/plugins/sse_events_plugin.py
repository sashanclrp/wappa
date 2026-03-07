"""SSEEventsPlugin - real-time full-payload event streaming over SSE."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...api.routes.sse import router as sse_router
from ...core.logging.logger import get_app_logger
from ...core.sse import (
    SSEErrorHandler,
    SSEEventHub,
    SSEMessageHandler,
    SSEStatusHandler,
    publish_api_sse_event,
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
    ):
        self.publish_incoming = publish_incoming
        self.publish_outgoing_api = publish_outgoing_api
        self.publish_bot_replies = publish_bot_replies
        self.publish_status = publish_status
        self.publish_webhook_errors = publish_webhook_errors
        self.queue_size = queue_size

        self._original_message_handler = None
        self._original_status_handler = None
        self._original_error_handler = None
        self._original_post_process_api = None

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
        self._original_post_process_api = event_handler._post_process_api_message

        handlers_wrapped: list[str] = []

        if self.publish_incoming:
            event_handler._default_message_handler = SSEMessageHandler(
                event_hub=event_hub,
                inner_handler=self._original_message_handler,
            )
            handlers_wrapped.append("incoming_message")

        if self.publish_status:
            event_handler._default_status_handler = SSEStatusHandler(
                event_hub=event_hub,
                inner_handler=self._original_status_handler,
            )
            handlers_wrapped.append("status_change")

        if self.publish_webhook_errors:
            event_handler._default_error_handler = SSEErrorHandler(
                event_hub=event_hub,
                inner_handler=self._original_error_handler,
            )
            handlers_wrapped.append("webhook_error")

        if self.publish_outgoing_api and self._original_post_process_api is not None:
            original = self._original_post_process_api

            async def wrapped_post_process(event: APIMessageEvent) -> None:
                await original(event)
                await publish_api_sse_event(event_hub, event)

            event_handler._post_process_api_message = wrapped_post_process
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
        api_dispatcher = getattr(app.state, "api_event_dispatcher", None)
        event_handler = getattr(api_dispatcher, "_event_handler", None)

        if event_handler:
            if self._original_message_handler is not None:
                event_handler._default_message_handler = self._original_message_handler
            if self._original_status_handler is not None:
                event_handler._default_status_handler = self._original_status_handler
            if self._original_error_handler is not None:
                event_handler._default_error_handler = self._original_error_handler
            if self._original_post_process_api is not None:
                event_handler._post_process_api_message = (
                    self._original_post_process_api
                )

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
                "api_post_process": self._original_post_process_api is not None,
                "messenger_wrapper": getattr(app.state, "sse_wrap_messenger", False),
            },
            "hub": hub_stats,
        }
