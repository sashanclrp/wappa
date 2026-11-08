"""Lifecycle of Wappa's own scheduled-work trigger sources.

``Scheduling.from_app(app).dispatch(event)`` needs no plugin: a Host scheduler
can call it directly. This plugin starts and stops the two sources Wappa runs
itself, the Redis expiry listener and the built-in static crons.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...domain.inbox.identity import InboxRef
from ...persistence.redis.redis_client import PoolAlias
from ..expiry.dispatcher import ExpiryDispatcher, ExpirySubjectBinding
from ..expiry.listener import run_expiry_listener
from ..lifecycle.background_work_tracker import BackgroundWorkTracker
from ..logging.logger import get_app_logger
from ..scheduling.dispatch import Scheduling
from ..scheduling.static_cron import StaticCron, register_static_cron

if TYPE_CHECKING:
    import fastapi_crons
    from fastapi import APIRouter, FastAPI

    from ..events.event_handler import WappaEventHandler
    from ..factory.wappa_builder import WappaBuilder


class SchedulingPlugin:
    """Run the Redis expiry listener and static crons on the scheduled lane.

    Every trigger reaches ``WappaEventHandler.process_scheduled_event``.

    Example:
        async def subject(*, inbox_ref, action, identifier) -> str | None:
            return identifier if action in USER_ACTIONS else None

        app.add_plugin(
            SchedulingPlugin(redis_expiry=True, expiry_subjects=subject).add_cron(
                "daily_report", "0 9 * * *", inbox_ref=InboxRef.whatsapp("123")
            )
        )
    """

    def __init__(
        self,
        *,
        event_handler: WappaEventHandler | None = None,
        redis_expiry: bool = False,
        expiry_subjects: ExpirySubjectBinding | None = None,
        expiry_alias: PoolAlias = "expiry",
        expiry_reconnect_delay: int = 10,
        expiry_max_reconnect_attempts: int | None = None,
        include_cron_router: bool = True,
        cron_config: fastapi_crons.CronConfig | None = None,
    ) -> None:
        """
        Args:
            event_handler: Handler prototype, for ``WappaBuilder`` apps; ``Wappa``
                supplies the one from ``set_event_handler``.
            redis_expiry: Listen for Expiry Keys. Requires Redis.
            expiry_subjects: Maps an expired action and identifier to its subject
                User. Without it every expiry dispatches as Inbox-only work.
            expiry_alias: Redis pool holding Expiry Keys.
            expiry_reconnect_delay: Seconds to wait before reconnecting on error.
            expiry_max_reconnect_attempts: Reconnect limit (``None`` = unlimited).
            include_cron_router: Mount fastapi-crons monitoring at ``/crons`` when
                static crons are declared.
            cron_config: Optional fastapi-crons configuration.
        """
        if expiry_subjects is not None and not redis_expiry:
            raise ValueError("expiry_subjects requires redis_expiry=True")
        self.event_handler = event_handler
        self.redis_expiry = redis_expiry
        self.expiry_subjects = expiry_subjects
        self.expiry_alias = expiry_alias
        self.expiry_reconnect_delay = expiry_reconnect_delay
        self.expiry_max_reconnect_attempts = expiry_max_reconnect_attempts
        self.include_cron_router = include_cron_router
        self.cron_config = cron_config

        self._crons_declared: list[StaticCron] = []
        self._cron_router: APIRouter | None = None
        self._cron_engine: fastapi_crons.Crons | None = None
        self._listener_task: asyncio.Task[None] | None = None

    def add_cron(
        self,
        action: str,
        expr: str,
        *,
        inbox_ref: InboxRef | None = None,
        user_id: str | None = None,
        tags: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        max_retries: int = 0,
        retry_delay: float = 5.0,
        timeout: int = 120,
    ) -> SchedulingPlugin:
        """Declare a static cron; call before the application is built.

        Args:
            action: Unique name, delivered as ``ScheduledEvent.action``.
            expr: Cron expression, e.g. ``"0 9 * * *"``.
            inbox_ref: Inbox scope; omit for System work.
            user_id: Subject User; requires ``inbox_ref``.
            tags: Delivered in ``event.metadata["tags"]``.
            payload: Static data delivered in ``event.payload``.
            max_retries: Engine retries after a raised exception.
            retry_delay: Engine's initial retry delay in seconds.
            timeout: Engine's execution timeout in seconds.
        """
        if user_id is not None and inbox_ref is None:
            raise ValueError("A User-scoped cron requires inbox_ref")
        self._crons_declared.append(
            StaticCron(
                action=action,
                expr=expr,
                inbox_ref=inbox_ref,
                user_id=user_id,
                tags=tags or [],
                payload=payload or {},
                max_retries=max_retries,
                retry_delay=retry_delay,
                timeout=timeout,
            )
        )
        return self

    def configure(self, builder: WappaBuilder) -> None:
        """Start recovery after ordinary capability startup hooks are ready."""
        builder.add_startup_hook(self._publish_handler, priority=20)
        if self.redis_expiry:
            builder.add_startup_hook(self._start_expiry_listener, priority=95)
            builder.add_shutdown_hook(self._stop_expiry_listener, priority=80)
        if self._crons_declared:
            if self.include_cron_router:
                from fastapi import APIRouter

                self._cron_router = APIRouter()
                builder.add_router(
                    self._cron_router, prefix="/crons", tags=["Cron Jobs"]
                )
            builder.add_startup_hook(self._start_crons, priority=30)
            builder.add_shutdown_hook(self._stop_crons, priority=85)

    async def _publish_handler(self, app: FastAPI) -> None:
        if self.event_handler is not None:
            app.state.wappa_event_handler = self.event_handler
        if getattr(app.state, "wappa_event_handler", None) is None:
            raise RuntimeError(
                "SchedulingPlugin has no WappaEventHandler: call "
                "Wappa.set_event_handler() or pass event_handler="
            )

    async def _start_expiry_listener(self, app: FastAPI) -> None:
        from ...persistence.redis.redis_manager import RedisManager

        logger = get_app_logger()
        if not RedisManager.is_initialized():
            raise RuntimeError(
                "SchedulingPlugin(redis_expiry=True) requires Redis; "
                "use Wappa(cache='redis') or add RedisPlugin"
            )
        try:
            await RedisManager.get_client(self.expiry_alias)
        except Exception as exc:
            raise RuntimeError(
                f"Expiry pool {self.expiry_alias!r} is not configured: {exc}"
            ) from exc

        tracker = getattr(app.state, "background_work_tracker", None)
        if not isinstance(tracker, BackgroundWorkTracker):
            raise RuntimeError("BackgroundWorkTracker is not configured")

        # Resolved per expiry: this hook runs before later plugins publish the
        # capabilities the Dispatch Context builder captures on first use.
        async def run_event(event: Any) -> None:
            await Scheduling.from_app(app).run(event)

        self._listener_task = asyncio.create_task(
            run_expiry_listener(
                dispatcher=ExpiryDispatcher(
                    run_event=run_event,
                    tracker=tracker,
                    subjects=self.expiry_subjects,
                ),
                alias=self.expiry_alias,
                reconnect_delay=self.expiry_reconnect_delay,
                max_reconnect_attempts=self.expiry_max_reconnect_attempts,
            ),
            name="expiry_listener",
        )
        app.state.expiry_listener_task = self._listener_task
        logger.info("Redis expiry listener started (alias=%s)", self.expiry_alias)

    async def _stop_expiry_listener(self, app: FastAPI) -> None:
        logger = get_app_logger()
        task = self._listener_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
            except TimeoutError:
                logger.warning("Expiry listener did not shut down gracefully")
            except asyncio.CancelledError:
                logger.debug("Expiry listener cancelled")
        if hasattr(app.state, "expiry_listener_task"):
            del app.state.expiry_listener_task

    async def _start_crons(self, app: FastAPI) -> None:
        from fastapi_crons import Crons, get_cron_router

        self._cron_engine = Crons(app, config=self.cron_config)
        for cron in self._crons_declared:
            register_static_cron(self._cron_engine, cron, app)
        await self._cron_engine.start()

        # Populate the pre-registered router shell with fastapi-crons routes.
        # The router was included in the app's route tree during build() — with
        # FastAPI 0.137+ the tree preserves the original router reference, so
        # routes added here become routable without a second include_router call.
        if self._cron_router is not None:
            self._cron_router.include_router(get_cron_router())

        get_app_logger().info(
            "Static crons started: %d declared", len(self._crons_declared)
        )

    async def _stop_crons(self, app: FastAPI) -> None:
        """Stop the cron engine with bounded drain."""
        logger = get_app_logger()
        if self._cron_engine is None:
            return
        try:
            await asyncio.wait_for(self._cron_engine.stop(), timeout=15.0)
        except TimeoutError:
            logger.warning(
                "Static cron drain timed out after 15s: "
                "in-flight callbacks may have been interrupted"
            )
