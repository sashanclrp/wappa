"""Core Wappa plugin — logging, middleware, routes, and lifespan management."""

from typing import TYPE_CHECKING

from fastapi import FastAPI

from wappa.api.middleware.error_handler import ErrorHandlerMiddleware
from wappa.api.middleware.inbox import InboxMiddleware
from wappa.api.middleware.request_logging import RequestLoggingMiddleware
from wappa.api.routes.health import router as health_router
from wappa.api.routes.whatsapp_combined import whatsapp_router
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle

from ..config.settings import settings
from ..logging.logger import get_app_logger, setup_app_logging
from ..types import CacheType

if TYPE_CHECKING:
    from ..factory.wappa_builder import WappaBuilder


class WappaCorePlugin:
    """Core Wappa functionality implemented as a plugin."""

    def __init__(self, cache_type: CacheType = CacheType.MEMORY) -> None:
        self.cache_type = cache_type
        self._session_lifecycle: SessionLifecycle | None = None
        self._background_work_tracker: BackgroundWorkTracker | None = None

    def configure(self, builder: "WappaBuilder") -> None:
        logger = get_app_logger()
        logger.debug("🏗️ Configuring WappaCorePlugin...")

        # Higher priority numbers run closer to routes (inner middleware)
        builder.add_middleware(InboxMiddleware, priority=90)
        builder.add_middleware(ErrorHandlerMiddleware, priority=80)
        builder.add_middleware(RequestLoggingMiddleware, priority=70)

        builder.add_router(health_router)
        builder.add_router(whatsapp_router)

        builder.add_startup_hook(self._core_startup, priority=10)
        # Shutdown phases (highest priority runs first):
        # 90: mark draining — reject new background work
        # 70: drain tracked background tasks
        # 10: close HTTP session and clean up app state
        builder.add_shutdown_hook(self._begin_drain, priority=90)
        builder.add_shutdown_hook(self._drain_background_work, priority=70)
        builder.add_shutdown_hook(self._core_shutdown, priority=10)

        logger.debug(
            "✅ WappaCorePlugin configured - cache_type: %s, middleware: 3, routes: 2, hooks: 4",
            self.cache_type.value,
        )

    async def startup(self, app: FastAPI) -> None:
        """No-op — lifecycle managed by hooks registered in configure()."""

    async def shutdown(self, app: FastAPI) -> None:
        """No-op — lifecycle managed by hooks registered in configure()."""

    async def _core_startup(self, app: FastAPI) -> None:
        logger = None
        try:
            setup_app_logging()
            logger = get_app_logger()

            logger.info("🚀 Starting Wappa Framework v%s", settings.version)
            logger.info("📊 Environment: %s", settings.environment)
            logger.info("📥 Inbox ID: %s", settings.inbox_id)
            logger.info("📝 Log level: %s", settings.log_level)
            logger.info("💾 Cache type: %s", self.cache_type.value)

            if settings.is_development:
                logger.info("🔧 Development mode - logs: %s", settings.log_dir)

            app.state.wappa_cache_type = self.cache_type.value
            logger.debug(
                "💾 Set app.state.wappa_cache_type = %s", self.cache_type.value
            )

            logger.info("🌐 Creating persistent HTTP client...")
            client = SessionLifecycle._default_client_factory()
            self._session_lifecycle = SessionLifecycle(client)
            app.state.session_lifecycle = self._session_lifecycle
            app.state.http_session = client
            app.state.get_http_session = self._session_lifecycle.get_session
            logger.info(
                "✅ Persistent HTTP client created - connections: 100, keepalive: 20"
            )

            self._background_work_tracker = BackgroundWorkTracker()
            app.state.background_work_tracker = self._background_work_tracker

            base_url = (
                f"http://localhost:{settings.port}"
                if settings.is_development
                else "https://your-domain.com"
            )
            logger.info("=== AVAILABLE ENDPOINTS ===")
            logger.info("🏥 Health Check: %s/health", base_url)
            logger.info("📊 Detailed Health: %s/health/detailed", base_url)
            logger.info("📱 WhatsApp API: %s/api/whatsapp/...", base_url)
            if settings.is_development:
                logger.info("📖 API Documentation: %s/docs", base_url)
            else:
                logger.info("📖 API docs disabled in production")
            logger.info("============================")

            await self._display_webhook_urls(logger, base_url)

            logger.info("✅ Wappa core startup completed successfully")

        except Exception as e:
            if logger:
                logger.error("❌ Error during Wappa core startup: %s", e, exc_info=True)
            else:
                print(f"💥 Critical error during logging setup: {e}")  # noqa: T201
            raise

    async def _begin_drain(self, app: FastAPI) -> None:
        """Phase 1 (priority 90): mark runtime as draining."""
        logger = get_app_logger()
        logger.info("🛑 Wappa shutdown — marking runtime as draining")
        if self._session_lifecycle:
            self._session_lifecycle.begin_drain()
        if self._background_work_tracker:
            self._background_work_tracker.begin_drain()

    async def _drain_background_work(self, app: FastAPI) -> None:
        """Phase 2 (priority 70): drain remaining tracked background tasks."""
        if self._background_work_tracker:
            await self._background_work_tracker.drain(timeout=30.0)

    async def _core_shutdown(self, app: FastAPI) -> None:
        """Phase 3 (priority 10): close HTTP session and clean up app state."""
        logger = get_app_logger()
        logger.info("🛑 Closing Wappa core resources...")

        try:
            if self.cache_type == CacheType.MEMORY:
                try:
                    from wappa.persistence.memory.handlers.utils.memory_store import (
                        get_memory_store,
                    )

                    get_memory_store().stop_cleanup_task()
                    logger.debug("🧹 Memory store cleanup task stopped")
                except Exception as e:
                    logger.warning("Memory store cleanup stop failed: %s", e)

            if self._session_lifecycle:
                await self._session_lifecycle.close()
                logger.info("🌐 Persistent HTTP client closed cleanly")

            if hasattr(app.state, "wappa_cache_type"):
                del app.state.wappa_cache_type
                logger.debug("💾 Cache type cleared from app state")

            logger.info("✅ Wappa core shutdown completed")

        except Exception as e:
            logger.error("❌ Error during Wappa core shutdown: %s", e, exc_info=True)

    async def recreate_http_session(self, app: FastAPI) -> None:
        """Recreate the HTTP session after hot-reload or session failure.

        Serialized via lock — concurrent callers produce exactly one
        replacement session.  Raises RuntimeDrainingError if shutdown
        has begun.
        """
        if self._session_lifecycle is None:
            raise RuntimeError(
                "WappaCorePlugin.recreate_http_session() called before startup — "
                "ensure the plugin has started before requesting session recreation"
            )
        new_session = await self._session_lifecycle.recreate()
        app.state.http_session = new_session

    async def _display_webhook_urls(self, logger, base_url: str) -> None:
        try:
            # Imported here to avoid circular imports during startup
            from ..events.webhook_factory import webhook_url_factory

            whatsapp_webhook_url = webhook_url_factory.generate_whatsapp_webhook_url()

            logger.info("=== WHATSAPP WEBHOOK URL ===")
            logger.info("📍 Primary Webhook URL: %s", whatsapp_webhook_url)
            logger.info("   • Use this single URL in WhatsApp Business settings")
            logger.info("   • Handles both verification (GET) and webhooks (POST)")
            logger.info("   • Auto-configured with your WP_PHONE_ID from .env")
            logger.info("=============================")
            logger.info("")

        except Exception as e:
            logger.warning("⚠️ Could not generate webhook URL: %s", e)

    def get_cache_type(self) -> CacheType:
        return self.cache_type

    def set_cache_type(self, cache_type: CacheType) -> None:
        self.cache_type = cache_type
