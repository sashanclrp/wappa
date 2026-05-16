"""Core Wappa plugin — logging, middleware, routes, and lifespan management."""

from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI

from wappa.api.middleware.error_handler import ErrorHandlerMiddleware
from wappa.api.middleware.inbox import InboxMiddleware
from wappa.api.middleware.request_logging import RequestLoggingMiddleware
from wappa.api.routes.health import router as health_router
from wappa.api.routes.whatsapp_combined import whatsapp_router

from ..config.settings import settings
from ..logging.logger import get_app_logger, setup_app_logging
from ..types import CacheType

if TYPE_CHECKING:
    from ..factory.wappa_builder import WappaBuilder


class WappaCorePlugin:
    """Core Wappa functionality implemented as a plugin."""

    def __init__(self, cache_type: CacheType = CacheType.MEMORY) -> None:
        self.cache_type = cache_type

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
        builder.add_shutdown_hook(self._core_shutdown, priority=90)

        logger.debug(
            f"✅ WappaCorePlugin configured - cache_type: {self.cache_type.value}, "
            f"middleware: 3, routes: 2, hooks: 2"
        )

    async def startup(self, app: FastAPI) -> None:
        await self._core_startup(app)

    async def shutdown(self, app: FastAPI) -> None:
        await self._core_shutdown(app)

    async def _core_startup(self, app: FastAPI) -> None:
        logger = None
        try:
            setup_app_logging()
            logger = get_app_logger()

            logger.info(f"🚀 Starting Wappa Framework v{settings.version}")
            logger.info(f"📊 Environment: {settings.environment}")
            logger.info(f"📥 Inbox ID: {settings.inbox_id}")
            logger.info(f"📝 Log level: {settings.log_level}")
            logger.info(f"💾 Cache type: {self.cache_type.value}")

            if settings.is_development:
                logger.info(f"🔧 Development mode - logs: {settings.log_dir}")

            app.state.wappa_cache_type = self.cache_type.value
            logger.debug(f"💾 Set app.state.wappa_cache_type = {self.cache_type.value}")

            logger.info("🌐 Creating persistent HTTP client...")
            transport = httpx.AsyncHTTPTransport(
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                ),
            )
            app.state.http_session = httpx.AsyncClient(
                transport=transport, timeout=httpx.Timeout(30.0)
            )
            logger.info(
                "✅ Persistent HTTP client created - connections: 100, keepalive: 20"
            )

            base_url = (
                f"http://localhost:{settings.port}"
                if settings.is_development
                else "https://your-domain.com"
            )
            logger.info("=== AVAILABLE ENDPOINTS ===")
            logger.info(f"🏥 Health Check: {base_url}/health")
            logger.info(f"📊 Detailed Health: {base_url}/health/detailed")
            logger.info(f"📱 WhatsApp API: {base_url}/api/whatsapp/...")
            logger.info(
                f"📖 API Documentation: {base_url}/docs"
                if settings.is_development
                else "📖 API docs disabled in production"
            )
            logger.info("============================")

            await self._display_webhook_urls(logger, base_url)

            logger.info("✅ Wappa core startup completed successfully")

        except Exception as e:
            if logger:
                logger.error(f"❌ Error during Wappa core startup: {e}", exc_info=True)
            else:
                print(f"💥 Critical error during logging setup: {e}")
            raise

    async def _core_shutdown(self, app: FastAPI) -> None:
        logger = get_app_logger()
        logger.info("🛑 Starting Wappa core shutdown...")

        try:
            if hasattr(app.state, "http_session"):
                await app.state.http_session.aclose()
                logger.info("🌐 Persistent HTTP client closed cleanly")

            if hasattr(app.state, "wappa_cache_type"):
                del app.state.wappa_cache_type
                logger.debug("💾 Cache type cleared from app state")

            logger.info("✅ Wappa core shutdown completed")

        except Exception as e:
            logger.error(f"❌ Error during Wappa core shutdown: {e}", exc_info=True)

    async def _display_webhook_urls(self, logger, base_url: str) -> None:
        try:
            # Imported here to avoid circular imports during startup
            from ..events.webhook_factory import webhook_url_factory

            whatsapp_webhook_url = webhook_url_factory.generate_whatsapp_webhook_url()

            logger.info("=== WHATSAPP WEBHOOK URL ===")
            logger.info(f"📍 Primary Webhook URL: {whatsapp_webhook_url}")
            logger.info("   • Use this single URL in WhatsApp Business settings")
            logger.info("   • Handles both verification (GET) and webhooks (POST)")
            logger.info("   • Auto-configured with your WP_PHONE_ID from .env")
            logger.info("=============================")
            logger.info("")

        except Exception as e:
            logger.warning(f"⚠️ Could not generate webhook URL: {e}")

    def get_cache_type(self) -> CacheType:
        return self.cache_type

    def set_cache_type(self, cache_type: CacheType) -> None:
        self.cache_type = cache_type
