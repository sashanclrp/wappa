"""
Cron Plugin

Wraps fastapi-crons to provide scheduled background tasks that fire events
into the WappaEventHandler pipeline with full infrastructure access.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi_crons import CronConfig, Crons

    from ...core.context import WappaContextFactory
    from ...core.events.cron_event_dispatcher import CronEventDispatcher
    from ...core.events.event_handler import WappaEventHandler
    from ...core.factory.wappa_builder import WappaBuilder


@dataclass(frozen=True)
class _CronRegistration:
    """Internal registration record for a cron job."""

    cron_id: str
    expr: str
    tenant_id: str | None = None
    user_id: str | None = None
    tags: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    retry_delay: float = 5.0
    timeout: int = 120


class CronPlugin:
    """
    Plugin for scheduling cron jobs that fire into the event handler pipeline.

    Crons are registered via add_cron() before app startup. When a cron fires,
    the plugin creates a CronEvent, builds WappaContext (if tenant-scoped),
    clones the handler via with_context(), and dispatches to process_cron_event().

    Example:
        cron_plugin = CronPlugin(event_handler=handler)
        cron_plugin.add_cron(
            cron_id="daily_report",
            expr="0 9 * * *",
            tenant_id="acme",
            user_id="5551234567",
        )
        app.add_plugin(cron_plugin)
    """

    def __init__(
        self,
        event_handler: "WappaEventHandler",
        *,
        include_router: bool = True,
        config: "CronConfig | None" = None,
    ):
        """
        Initialize cron plugin.

        Args:
            event_handler: WappaEventHandler prototype for cloning
            include_router: Whether to mount fastapi-crons monitoring endpoints
            config: Optional CronConfig for distributed locking, etc.
        """
        self.event_handler = event_handler
        self.include_router = include_router
        self.config = config

        self._cron_registrations: list[_CronRegistration] = []

        # Set at startup
        self._crons: Crons | None = None
        self._context_factory: WappaContextFactory | None = None
        self._dispatcher: CronEventDispatcher | None = None

    def add_cron(
        self,
        cron_id: str,
        expr: str,
        *,
        tenant_id: str | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        max_retries: int = 0,
        retry_delay: float = 5.0,
        timeout: int = 120,
    ) -> "CronPlugin":
        """
        Register a cron job to fire as an event.

        Args:
            cron_id: Unique job name — used as dispatch key in process_cron_event()
            expr: Cron expression (e.g., "0 9 * * *" for daily at 9 AM)
            tenant_id: Optional tenant scope — if set, full context available
            user_id: Optional user scope — for messenger/cache targeting
            tags: Optional tags for secondary filtering
            payload: Optional static data available in the CronEvent
            max_retries: Max retry attempts on failure (default: 0)
            retry_delay: Initial retry delay in seconds (default: 5.0)
            timeout: Execution timeout in seconds (default: 120)

        Returns:
            Self for fluent API chaining
        """
        self._cron_registrations.append(
            _CronRegistration(
                cron_id=cron_id,
                expr=expr,
                tenant_id=tenant_id,
                user_id=user_id,
                tags=tags or [],
                payload=payload or {},
                max_retries=max_retries,
                retry_delay=retry_delay,
                timeout=timeout,
            )
        )
        return self

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the cron plugin with WappaBuilder.

        Registers startup/shutdown hooks at priority 30 (after core=10,
        infra=20, listeners=25).

        Args:
            builder: WappaBuilder instance
        """
        builder.add_startup_hook(self._startup_hook, priority=30)
        builder.add_shutdown_hook(self._shutdown_hook, priority=30)

        logger = get_app_logger()
        logger.debug(
            f"CronPlugin configured with {len(self._cron_registrations)} cron(s)"
        )

    async def _startup_hook(self, app: "FastAPI") -> None:
        """
        Initialize fastapi-crons scheduler and register all cron jobs.

        Runs at startup priority 30 (after core=10, infra=20, listeners=25).
        """
        from fastapi_crons import Crons, get_cron_router

        from ...core.context import WappaContextFactory
        from ...core.events.cron_event_dispatcher import CronEventDispatcher

        # Init/reuse WappaContextFactory on app.state
        if not hasattr(app.state, "wappa_context_factory"):
            app.state.wappa_context_factory = WappaContextFactory(app)
        self._context_factory = app.state.wappa_context_factory
        self._dispatcher = CronEventDispatcher()

        # Initialize fastapi-crons
        self._crons = Crons(app, config=self.config)

        # Register each cron as an internal job
        for reg in self._cron_registrations:
            self._register_cron_job(reg)

        # Start the scheduler
        await self._crons.start()

        # Optionally mount monitoring router
        if self.include_router:
            cron_router = get_cron_router()
            app.include_router(cron_router, prefix="/crons", tags=["Cron Jobs"])

        # Store on app.state for monitoring
        app.state.cron_plugin = self

        logger = get_app_logger()
        logger.info(f"CronPlugin started with {len(self._cron_registrations)} cron(s)")

    def _register_cron_job(self, reg: _CronRegistration) -> None:
        """
        Register a single cron job with fastapi-crons.

        Creates a closure that captures the registration data and bridges
        the cron execution into the Wappa event pipeline.
        """

        @self._crons.cron(
            expr=reg.expr,
            name=reg.cron_id,
            tags=reg.tags,
            max_retries=reg.max_retries,
            retry_delay=reg.retry_delay,
            timeout=reg.timeout,
        )
        async def _callback():
            await self._fire_cron_event(reg)

    async def _fire_cron_event(self, reg: _CronRegistration) -> None:
        """
        Fire a cron event through the Wappa event pipeline.

        Pipeline:
        1. Create CronEvent from registration data + timestamp
        2. Create WappaContext (tenant-scoped or db-only for system crons)
        3. Clone handler via with_context()
        4. Dispatch via CronEventDispatcher
        """
        from wappa.domain.events.cron_event import CronEvent

        logger = get_app_logger()
        now = datetime.now(UTC)

        event = CronEvent(
            cron_id=reg.cron_id,
            cron_expr=reg.expr,
            tags=reg.tags,
            tenant_id=reg.tenant_id,
            user_id=reg.user_id,
            payload=reg.payload,
            metadata={"actual_time": now.isoformat()},
            timestamp=now,
        )

        try:
            request_handler = await self._create_request_handler(reg)
            result = await self._dispatcher.dispatch(event, request_handler)

            if not result.get("success"):
                logger.error(
                    f"Cron event dispatch failed for {reg.cron_id}: "
                    f"{result.get('error')}"
                )

        except Exception as e:
            logger.error(
                f"Error firing cron event {reg.cron_id}: {e}",
                exc_info=True,
            )

    async def _create_request_handler(
        self, reg: _CronRegistration
    ) -> "WappaEventHandler":
        """
        Create a context-bound handler clone for a cron execution.

        Tenant-scoped crons get full context (messenger, cache, db).
        System crons (no tenant_id) get db-only context.
        """
        if reg.tenant_id and self._context_factory:
            ctx = await self._context_factory.create_context(
                tenant_id=reg.tenant_id,
                user_id=reg.user_id,
                include_messenger=reg.user_id is not None,
            )
            return self.event_handler.with_context(
                tenant_id=reg.tenant_id,
                user_id=reg.user_id or "",
                messenger=ctx.messenger,
                cache_factory=ctx.cache_factory,
                db=ctx.db,
                db_read=ctx.db_read,
            )

        # System cron: db-only context
        tenant_id = reg.tenant_id or "__system__"
        if self._context_factory:
            ctx = await self._context_factory.create_context(tenant_id=tenant_id)
            return self.event_handler.with_context(
                tenant_id=tenant_id,
                user_id="",
                messenger=None,
                cache_factory=None,
                db=ctx.db,
                db_read=ctx.db_read,
            )

        return self.event_handler.with_context(
            tenant_id=tenant_id,
            user_id="",
            messenger=None,
            cache_factory=None,
        )

    async def _shutdown_hook(self, app: "FastAPI") -> None:
        """Stop the cron scheduler and clean up app.state."""
        logger = get_app_logger()

        if self._crons:
            await self._crons.stop()
            logger.info("CronPlugin scheduler stopped")

        if hasattr(app.state, "cron_plugin"):
            del app.state.cron_plugin

    async def startup(self, app: "FastAPI") -> None:
        """No-op — lifecycle managed by startup/shutdown hooks registered in configure()."""

    async def shutdown(self, app: "FastAPI") -> None:
        """No-op — lifecycle managed by startup/shutdown hooks registered in configure()."""
