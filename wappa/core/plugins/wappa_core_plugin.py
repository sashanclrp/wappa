"""Core Wappa plugin — logging, middleware, routes, and lifespan management."""

from typing import TYPE_CHECKING

from fastapi import FastAPI

from wappa.api.middleware.error_handler import ErrorHandlerMiddleware
from wappa.api.middleware.inbox import InboxMiddleware
from wappa.api.middleware.request_id import RequestIdMiddleware
from wappa.api.middleware.request_logging import RequestLoggingMiddleware
from wappa.api.routes.health import router as health_router
from wappa.api.routes.whatsapp_combined import create_whatsapp_router
from wappa.core.lifecycle import BackgroundWorkTracker, SessionLifecycle

from ..config.settings import settings
from ..logging.logger import ContextLogger, get_app_logger, setup_app_logging
from ..types import CacheType

if TYPE_CHECKING:
    from ..factory.wappa_builder import WappaBuilder


class WappaCorePlugin:
    """Core Wappa functionality implemented as a plugin."""

    def __init__(
        self,
        cache_type: CacheType = CacheType.MEMORY,
        *,
        route_profile: str | None = None,
        include_template_transport_api: bool | None = None,
        include_outbound_transport_api: bool | None = None,
        include_media_management_api: bool | None = None,
        include_media_upload_api: bool | None = None,
        include_state_handler_api: bool | None = None,
    ) -> None:
        self.cache_type = cache_type
        self.route_profile = route_profile
        self.include_template_transport_api = include_template_transport_api
        self.include_outbound_transport_api = include_outbound_transport_api
        self.include_media_management_api = include_media_management_api
        self.include_media_upload_api = include_media_upload_api
        self.include_state_handler_api = include_state_handler_api
        self._session_lifecycle: SessionLifecycle | None = None
        self._background_work_tracker: BackgroundWorkTracker | None = None

    def configure(self, builder: "WappaBuilder") -> None:
        logger = get_app_logger()
        logger.debug("🏗️ Configuring WappaCorePlugin...")

        # Higher priority numbers run closer to routes (inner middleware).
        # RequestIdMiddleware is outermost so the correlation ID exists for
        # every downstream middleware, route, log line, and error response.
        builder.with_persistence_backend(self.cache_type.value)
        builder.add_middleware(InboxMiddleware, priority=90)
        builder.add_middleware(ErrorHandlerMiddleware, priority=80)
        builder.add_middleware(RequestLoggingMiddleware, priority=70)
        builder.add_middleware(RequestIdMiddleware, priority=60)

        builder.add_router(health_router, public=True)
        builder.add_router(
            create_whatsapp_router(
                profile=self.route_profile,
                include_template_transport=self.include_template_transport_api,
                include_outbound_transport=self.include_outbound_transport_api,
                include_media_management=self.include_media_management_api,
                include_media_upload=self.include_media_upload_api,
                include_state_handler_api=self.include_state_handler_api,
            )
        )

        builder.add_startup_hook(self._core_startup, priority=10)
        # Shutdown phases (highest priority runs first):
        # 90: mark draining — reject new background work
        # 70: drain tracked background tasks
        # 10: close HTTP session and clean up app state
        builder.add_shutdown_hook(self._begin_drain, priority=90)
        builder.add_shutdown_hook(self._drain_background_work, priority=70)
        builder.add_shutdown_hook(self._core_shutdown, priority=10)

        logger.debug(
            "✅ WappaCorePlugin configured - cache_type: %s, middleware: 4, routes: 2, hooks: 4",
            self.cache_type.value,
        )

    async def _core_startup(self, app: FastAPI) -> None:
        logger = None
        try:
            setup_app_logging()
            logger = get_app_logger()

            logger.info("🚀 Starting Wappa Framework v%s", settings.version)
            logger.info("📊 Environment: %s", settings.environment)
            inbox_runtime = getattr(app.state, "inbox_runtime", None)
            if inbox_runtime is None:
                raise RuntimeError(
                    "app.state.inbox_runtime is not set — build the application "
                    "through Wappa or WappaBuilder so an Inbox Routing Mode is "
                    "assembled before startup"
                )
            logger.info("📥 Inbox routing mode: %s", inbox_runtime.mode.value)
            if inbox_runtime.default_inbox_ref is not None:
                logger.info(
                    "📥 Legacy default Inbox: %s",
                    inbox_runtime.default_inbox_ref.inbox_id,
                )
            else:
                logger.info("📥 Inbox Directory: configured (explicit mode)")
            meta_config = getattr(app.state, "meta_application_config", None)
            logger.info(
                "🔐 Meta callback authentication: %s",
                "configured" if meta_config is not None else "not mounted",
            )
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

            await self._display_webhook_urls(app, logger, base_url)

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

    async def recreate_http_session(self) -> None:
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
        await self._session_lifecycle.recreate()

    async def _display_webhook_urls(
        self, app: FastAPI, logger: ContextLogger, base_url: str
    ) -> None:
        try:
            # Imported here to avoid circular imports during startup
            from ..events.webhook_factory import webhook_url_factory

            logger.info("=== WHATSAPP WEBHOOK URL ===")
            logger.info(
                "📍 WhatsApp Webhook URL: %s",
                webhook_url_factory.generate_whatsapp_webhook_url(),
            )
            logger.info("   • Configure this one URL in the Meta App")
            logger.info("   • POST bodies are authenticated with META_APP_SECRET")
            logger.info("   • POST routing uses metadata.phone_number_id or WABA scope")
            logger.info("   • Handles both verification (GET) and webhooks (POST)")
            logger.info("=============================")
            logger.info("")

        except Exception as e:
            logger.warning("⚠️ Could not generate webhook URL: %s", e)

    def get_cache_type(self) -> CacheType:
        return self.cache_type

    def set_cache_type(self, cache_type: CacheType) -> None:
        self.cache_type = cache_type
