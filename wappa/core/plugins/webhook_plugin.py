"""
Webhook Plugin - External webhook processor integration.

Specialized plugin for adding external webhook endpoints to Wappa applications.
Uses IWebhookProcessor for full Wappa infrastructure access.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

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
    ):
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

    def configure(self, builder: WappaBuilder) -> None:
        logger = get_app_logger()
        tags = [f"{self.external_source.title()} Webhooks"]

        if self.include_inbox_id:

            @self.router.api_route(
                "/{inbox_id}",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def webhook_endpoint(request: Request, inbox_id: str):
                return await self._handle_webhook(request, inbox_id)

        else:

            @self.router.api_route(
                "/",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def webhook_endpoint(request: Request):
                return await self._handle_webhook(request, None)

        status_path = "/{inbox_id}/status" if self.include_inbox_id else "/status"

        @self.router.get(status_path, tags=tags)
        async def webhook_status(request: Request, inbox_id: str = None):
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

        builder.add_router(self.router, prefix=self.prefix)
        builder.add_startup_hook(self._init_dependencies, priority=30)

        logger.debug(
            f"WebhookPlugin configured for {self.external_source} - "
            f"Prefix: {self.prefix}, Methods: {self.methods}"
        )

    async def _init_dependencies(self, app: FastAPI) -> None:
        from ...core.context import WappaContextFactory
        from ...core.events.external_event_dispatcher import ExternalEventDispatcher

        if not hasattr(app.state, "wappa_context_factory"):
            app.state.wappa_context_factory = WappaContextFactory(app)

        self._context_factory = app.state.wappa_context_factory
        self._external_dispatcher = ExternalEventDispatcher()

        get_app_logger().info(
            f"WebhookPlugin processor initialized for {self.external_source}"
        )

    async def _handle_webhook(
        self,
        request: Request,
        inbox_id: str | None,
    ) -> dict:
        if not inbox_id:
            return {
                "status": "error",
                "detail": "inbox_id is required for processor mode",
            }

        await request.body()

        asyncio.create_task(self._process_webhook_async(request, inbox_id))
        return {"status": "accepted"}

    async def _process_webhook_async(
        self,
        request: Request,
        inbox_id: str,
    ) -> None:
        logger = get_app_logger()

        try:
            event = await self.processor.parse_event(request, inbox_id)
            logger.info(
                f"Parsed external event: {event.source}/{event.event_type} "
                f"(inbox={inbox_id})"
            )

            ctx = await self._context_factory.create_context(inbox_id)

            user_id = await self.processor.resolve_user_id(event, ctx.db)
            event.user_id = user_id

            if user_id:
                ctx = await self._context_factory.create_context(
                    inbox_id=inbox_id,
                    user_id=user_id,
                    include_messenger=True,
                )

            request_handler = self.event_handler.with_context(
                inbox_id=inbox_id,
                user_id=user_id or "",
                messenger=ctx.messenger,
                cache_factory=ctx.cache_factory,
                db=ctx.db,
                db_read=ctx.db_read,
            )

            result = await self._external_dispatcher.dispatch(event, request_handler)

            if not result.get("success"):
                logger.error(
                    f"External event dispatch failed for {self.external_source}: "
                    f"{result.get('error')}"
                )

        except Exception as e:
            logger.error(
                f"Error processing external webhook for {self.external_source}, "
                f"inbox={inbox_id}: {e}",
                exc_info=True,
            )

    async def startup(self, app: FastAPI) -> None:
        url_pattern = (
            f"{self.prefix}/{{inbox_id}}"
            if self.include_inbox_id
            else f"{self.prefix}/"
        )
        get_app_logger().info(
            f"WebhookPlugin for {self.external_source} ready - "
            f"URL pattern: {url_pattern}, Methods: {self.methods}"
        )

    async def shutdown(self, app: FastAPI) -> None:
        get_app_logger().debug(
            f"WebhookPlugin for {self.external_source} shutting down"
        )
