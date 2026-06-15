"""
Webhook Plugin - External webhook processor integration.

Specialized plugin for adding external webhook endpoints to Wappa applications.
Uses IWebhookProcessor for full Wappa infrastructure access.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request

from ...core.external_webhooks import ExternalWebhookRuntime, clone_request_with_body
from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.context import WappaContextFactory
    from ...core.events.event_handler import WappaEventHandler
    from ...core.events.external_event_dispatcher import ExternalEventDispatcher
    from ...core.factory.wappa_builder import WappaBuilder
    from ...domain.interfaces.webhook_processor import IWebhookProcessor


class WebhookPlugin:
    """
    Plugin for adding external webhook endpoints.

    Example:
        WebhookPlugin(
            "mercadopago",
            processor=MercadoPagoProcessor(),
            event_handler=handler,
        )
    """

    def __init__(
        self,
        external_source: str,
        *,
        processor: IWebhookProcessor,
        event_handler: WappaEventHandler,
        prefix: str | None = None,
        methods: list[str] | None = None,
        include_inbox_id: bool = True,
        **route_kwargs: Any,
    ) -> None:
        self.external_source = external_source
        self.processor = processor
        self.event_handler = event_handler
        self.prefix = prefix or f"/webhook/{external_source}"
        self.methods = methods or ["POST"]
        self.include_inbox_id = include_inbox_id
        self.route_kwargs = route_kwargs

        self.router = APIRouter()

        self._context_factory: WappaContextFactory | None = None
        self._external_dispatcher: ExternalEventDispatcher | None = None
        self._runtime: ExternalWebhookRuntime | None = None

    def configure(self, builder: WappaBuilder) -> None:
        logger = get_app_logger()
        tags: list[str | Enum] = [f"{self.external_source.title()} Webhooks"]

        if self.include_inbox_id:

            @self.router.api_route(
                "/{inbox_id}",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def inbox_webhook_endpoint(
                request: Request, inbox_id: str
            ) -> dict[str, str]:
                return await self._handle_webhook(request, inbox_id)

        else:

            @self.router.api_route(
                "/",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def source_webhook_endpoint(request: Request) -> dict[str, str]:
                return await self._handle_webhook(request, None)

        status_path = "/{inbox_id}/status" if self.include_inbox_id else "/status"

        @self.router.get(status_path, tags=tags)
        async def webhook_status(
            request: Request, inbox_id: str | None = None
        ) -> dict[str, Any]:
            base_url = str(request.base_url).rstrip("/")
            webhook_url = f"{base_url}{self.prefix}"
            if inbox_id:
                webhook_url = f"{webhook_url}/{inbox_id}"
            return {
                "status": "active",
                "external_source": self.external_source,
                "inbox_id": inbox_id,
                "webhook_url": webhook_url,
                "methods": self.methods,
            }

        builder.add_router(self.router, prefix=self.prefix, public=True)
        builder.add_startup_hook(self._init_dependencies, priority=30)

        logger.debug(
            "WebhookPlugin configured for %s - Prefix: %s, Methods: %s",
            self.external_source,
            self.prefix,
            self.methods,
        )

    async def _init_dependencies(self, app: FastAPI) -> None:
        from ...core.context import WappaContextFactory
        from ...core.events.external_event_dispatcher import ExternalEventDispatcher

        if not hasattr(app.state, "wappa_context_factory"):
            app.state.wappa_context_factory = WappaContextFactory(app)

        self._context_factory = app.state.wappa_context_factory
        self._external_dispatcher = ExternalEventDispatcher()
        processor_source = self.processor.get_source_name()
        if processor_source != self.external_source:
            raise ValueError(
                "WebhookPlugin external_source must match processor.get_source_name(): "
                f"{self.external_source!r} != {processor_source!r}"
            )
        self._runtime = ExternalWebhookRuntime(
            external_source=self.external_source,
            processor=self.processor,
            event_handler=self.event_handler,
            context_factory=self._context_factory,
            dispatcher=self._external_dispatcher,
        )

        get_app_logger().info(
            "WebhookPlugin processor initialized for %s", self.external_source
        )

    async def _handle_webhook(
        self,
        request: Request,
        inbox_id: str | None,
    ) -> dict[str, str]:
        if not inbox_id:
            raise HTTPException(
                status_code=400,
                detail="inbox_id is required for External Webhook Source processing",
            )
        if self._runtime is None:
            raise RuntimeError(
                "WebhookPlugin runtime not initialized — ensure the application "
                "lifespan has started before processing external webhooks"
            )

        body = await request.body()
        request_snapshot = clone_request_with_body(request, body)

        tracker = getattr(request.app.state, "background_work_tracker", None)
        if not tracker:
            raise RuntimeError(
                "BackgroundWorkTracker not available in app.state — "
                "WappaCorePlugin must be configured and started before "
                "processing external webhooks"
            )
        tracker.track(
            self._runtime.process(request_snapshot, inbox_id),
            name=f"webhook:{self.external_source}:{inbox_id}",
        )
        return {"status": "accepted"}

