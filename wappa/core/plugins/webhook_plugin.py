"""
Webhook Plugin v2

Specialized plugin for adding webhook endpoints to Wappa applications.
Supports two modes:
1. Raw handler (v1 backwards compat): handler(request, tenant_id, provider) -> dict
2. Processor mode (v2): IWebhookProcessor with full Wappa infrastructure access
"""

import asyncio
from collections.abc import Callable
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
    Plugin for adding specialized webhook endpoints.

    Supports two modes:

    **Raw handler mode (v1)**: Pass a handler callable.
        WebhookPlugin("wompi", wompi_webhook_handler)

    **Processor mode (v2)**: Pass an IWebhookProcessor for full Wappa
    infrastructure access (messenger, cache, database).
        WebhookPlugin(
            "mercadopago",
            processor=MercadoPagoProcessor(),
            event_handler=handler,
        )
    """

    def __init__(
        self,
        provider: str,
        handler: Callable | None = None,
        *,
        processor: "IWebhookProcessor | None" = None,
        event_handler: "WappaEventHandler | None" = None,
        prefix: str | None = None,
        methods: list[str] | None = None,
        include_tenant_id: bool = True,
        **route_kwargs: Any,
    ):
        """
        Initialize webhook plugin.

        Args:
            provider: Provider name (e.g., 'mercadopago', 'stripe')
            handler: Raw handler callable (v1 mode)
            processor: IWebhookProcessor instance (v2 mode)
            event_handler: WappaEventHandler prototype for cloning (v2 mode)
            prefix: URL prefix (defaults to /webhook/{provider})
            methods: HTTP methods to accept (defaults to ['POST'])
            include_tenant_id: Whether to include tenant_id in the URL path
            **route_kwargs: Additional arguments for FastAPI route decorator

        Raises:
            ValueError: If neither handler nor processor provided,
                        or if processor provided without event_handler
        """
        if handler is None and processor is None:
            raise ValueError("Either handler or processor must be provided")
        if processor is not None and event_handler is None:
            raise ValueError("event_handler is required when using processor mode")

        self.provider = provider
        self.handler = handler
        self.processor = processor
        self.event_handler = event_handler
        self.prefix = prefix or f"/webhook/{provider}"
        self.methods = methods or ["POST"]
        self.include_tenant_id = include_tenant_id
        self.route_kwargs = route_kwargs

        self.router = APIRouter()

        # Set at startup (processor mode only)
        self._context_factory: WappaContextFactory | None = None
        self._external_dispatcher: ExternalEventDispatcher | None = None

    @property
    def is_processor_mode(self) -> bool:
        """Check if this plugin uses v2 processor mode."""
        return self.processor is not None

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the webhook plugin with WappaBuilder.

        Args:
            builder: WappaBuilder instance
        """
        logger = get_app_logger()
        tags = [f"{self.provider.title()} Webhooks"]

        # Create webhook endpoint based on tenant_id inclusion
        if self.include_tenant_id:

            @self.router.api_route(
                "/{tenant_id}",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def webhook_endpoint(request: Request, tenant_id: str):
                if self.is_processor_mode:
                    return await self._handle_processor_webhook(request, tenant_id)
                return await self.handler(request, tenant_id, self.provider)

        else:

            @self.router.api_route(
                "/",
                methods=self.methods,
                tags=tags,
                **self.route_kwargs,
            )
            async def webhook_endpoint(request: Request):
                if self.is_processor_mode:
                    return await self._handle_processor_webhook(request, None)
                return await self.handler(request, None, self.provider)

        # Status endpoint for webhook health checks
        status_path = "/{tenant_id}/status" if self.include_tenant_id else "/status"

        @self.router.get(status_path, tags=tags)
        async def webhook_status(request: Request, tenant_id: str = None):
            base_url = str(request.base_url).rstrip("/")
            webhook_url = f"{base_url}{self.prefix}"
            if tenant_id:
                webhook_url = f"{webhook_url}/{tenant_id}"
            return {
                "status": "active",
                "provider": self.provider,
                "tenant_id": tenant_id,
                "webhook_url": webhook_url,
                "methods": self.methods,
                "mode": "processor" if self.is_processor_mode else "raw",
            }

        builder.add_router(self.router, prefix=self.prefix)

        if self.is_processor_mode:
            builder.add_startup_hook(self._init_processor_mode, priority=30)

        mode = "processor" if self.is_processor_mode else "raw"
        logger.debug(
            f"WebhookPlugin configured for {self.provider} - "
            f"Mode: {mode}, Prefix: {self.prefix}, Methods: {self.methods}"
        )

    async def _init_processor_mode(self, app: "FastAPI") -> None:
        """
        Initialize processor mode dependencies during app startup.

        Runs at startup priority 30 (after core=10, infra=20, listeners=25).
        """
        from ...core.context import WappaContextFactory
        from ...core.events.external_event_dispatcher import ExternalEventDispatcher

        if not hasattr(app.state, "wappa_context_factory"):
            app.state.wappa_context_factory = WappaContextFactory(app)

        self._context_factory = app.state.wappa_context_factory
        self._external_dispatcher = ExternalEventDispatcher()

        logger = get_app_logger()
        logger.info(f"WebhookPlugin v2 processor mode initialized for {self.provider}")

    async def _handle_processor_webhook(
        self,
        request: Request,
        tenant_id: str | None,
    ) -> dict:
        """
        Handle webhook using processor mode (v2).

        Caches the request body (Starlette streams are read-once), then
        returns 200 immediately and processes in a background task.
        """
        if not tenant_id:
            return {
                "status": "error",
                "detail": "tenant_id is required for processor mode",
            }

        # Cache request body before background task (Starlette caches
        # internally after first read, so request.json() works in the task)
        await request.body()

        asyncio.create_task(self._process_webhook_async(request, tenant_id))
        return {"status": "accepted"}

    async def _process_webhook_async(
        self,
        request: Request,
        tenant_id: str,
    ) -> None:
        """
        Background webhook processing pipeline:
        1. processor.parse_event() -> ExternalEvent
        2. context_factory.create_context(tenant_id) -> WappaContext (DB only)
        3. processor.resolve_user_id(event, db) -> user_id
        4. context_factory.create_context(tenant_id, user_id) -> full context
        5. event_handler.with_context() -> cloned handler
        6. external_dispatcher.dispatch(event, handler) -> result
        """
        logger = get_app_logger()

        try:
            event = await self.processor.parse_event(request, tenant_id)
            logger.info(
                f"Parsed external event: {event.source}/{event.event_type} "
                f"(tenant={tenant_id})"
            )

            # Create initial context (tenant-only, for DB access during user resolution)
            ctx = await self._context_factory.create_context(tenant_id)

            # Resolve user_id from event payload (may require DB lookup)
            user_id = await self.processor.resolve_user_id(event, ctx.db)
            event.user_id = user_id

            # Upgrade context with user_id for cache + messenger
            if user_id:
                ctx = await self._context_factory.create_context(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    include_messenger=True,
                )

            # Clone handler with full context (same pattern as WebhookController)
            request_handler = self.event_handler.with_context(
                tenant_id=tenant_id,
                user_id=user_id or "",
                messenger=ctx.messenger,
                cache_factory=ctx.cache_factory,
                db=ctx.db,
                db_read=ctx.db_read,
            )

            result = await self._external_dispatcher.dispatch(event, request_handler)

            if not result.get("success"):
                logger.error(
                    f"External event dispatch failed for {self.provider}: "
                    f"{result.get('error')}"
                )

        except Exception as e:
            logger.error(
                f"Error processing external webhook for {self.provider}, "
                f"tenant={tenant_id}: {e}",
                exc_info=True,
            )

    async def startup(self, app: "FastAPI") -> None:
        """Execute webhook plugin startup logic."""
        logger = get_app_logger()
        url_pattern = (
            f"{self.prefix}/{{tenant_id}}"
            if self.include_tenant_id
            else f"{self.prefix}/"
        )
        mode = "processor" if self.is_processor_mode else "raw"
        logger.info(
            f"WebhookPlugin for {self.provider} ready - "
            f"URL pattern: {url_pattern}, Methods: {self.methods}, Mode: {mode}"
        )

    async def shutdown(self, app: "FastAPI") -> None:
        """Execute webhook plugin cleanup logic."""
        logger = get_app_logger()
        logger.debug(f"WebhookPlugin for {self.provider} shutting down")
