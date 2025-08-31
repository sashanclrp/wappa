"""
Wappa Core Plugin

This plugin encapsulates all traditional Wappa functionality, providing the foundation
for the Wappa framework through the plugin system. It includes logging, middleware,
routes, and lifespan management that was previously hardcoded in the Wappa class.
"""

from typing import TYPE_CHECKING

import aiohttp
from fastapi import FastAPI

from wappa.api.middleware.error_handler import ErrorHandlerMiddleware
from wappa.api.middleware.owner import OwnerMiddleware
from wappa.api.middleware.request_logging import RequestLoggingMiddleware
from wappa.api.routes.health import router as health_router
from wappa.api.routes.whatsapp_combined import whatsapp_router

from ..config.settings import settings
from ..logging.logger import get_app_logger, setup_app_logging
from ..types import CacheType

if TYPE_CHECKING:
    from ..factory.wappa_builder import WappaBuilder


class WappaCorePlugin:
    """
    Core Wappa functionality as a plugin.

    This plugin provides all the essential Wappa framework functionality:
    - Application logging setup
    - HTTP session management
    - Core middleware stack (Owner, ErrorHandler, RequestLogging)
    - Core routes (Health, WhatsApp combined)
    - Webhook URL generation and logging
    - Cache type configuration

    By implementing core functionality as a plugin, we achieve a unified
    architecture where all Wappa applications use the same plugin-based
    foundation, whether they use simple Wappa() or advanced WappaBuilder.
    """

    def __init__(self, cache_type: CacheType = CacheType.MEMORY):
        """
        Initialize Wappa core plugin.

        Args:
            cache_type: Cache backend to use for the application
        """
        self.cache_type = cache_type

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure core Wappa functionality with the builder.

        Registers:
        - Core middleware with appropriate priorities
        - Core routes (health, whatsapp)
        - Core startup/shutdown hooks

        Args:
            builder: WappaBuilder instance to configure
        """
        logger = get_app_logger()
        logger.debug("🏗️ Configuring WappaCorePlugin...")

        # Register core middleware with proper priorities
        # Higher priority numbers run closer to routes (inner middleware)
        builder.add_middleware(
            OwnerMiddleware, priority=90
        )  # Outer - tenant extraction
        builder.add_middleware(ErrorHandlerMiddleware, priority=80)  # Error handling
        builder.add_middleware(
            RequestLoggingMiddleware, priority=70
        )  # Request logging (inner)

        # Register core routes
        builder.add_router(health_router)
        builder.add_router(whatsapp_router)

        # Register core lifespan hooks with high priority (runs first/last)
        builder.add_startup_hook(self._core_startup, priority=10)  # First to run
        builder.add_shutdown_hook(self._core_shutdown, priority=90)  # Last to run

        logger.debug(
            f"✅ WappaCorePlugin configured - cache_type: {self.cache_type.value}, "
            f"middleware: 3, routes: 2, hooks: 2"
        )

    async def startup(self, app: FastAPI) -> None:
        """
        Plugin startup method required by WappaPlugin protocol.

        Delegates to _core_startup hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._core_startup(app)

    async def shutdown(self, app: FastAPI) -> None:
        """
        Plugin shutdown method required by WappaPlugin protocol.

        Delegates to _core_shutdown hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._core_shutdown(app)

    async def _core_startup(self, app: FastAPI) -> None:
        """
        Core Wappa startup functionality.

        This hook runs first (priority 10) to establish the foundation that
        other plugins and hooks can depend on:
        - Logging system initialization
        - HTTP session for connection pooling
        - Cache type configuration
        - Webhook URL generation and display
        - Development mode configuration

        Args:
            app: FastAPI application instance
        """
        logger = None
        try:
            # Initialize logging first - this is critical for all other operations
            setup_app_logging()
            logger = get_app_logger()

            logger.info(f"🚀 Starting Wappa Framework v{settings.version}")
            logger.info(f"📊 Environment: {settings.environment}")
            logger.info(f"👤 Owner ID: {settings.owner_id}")
            logger.info(f"📝 Log level: {settings.log_level}")
            logger.info(f"💾 Cache type: {self.cache_type.value}")

            if settings.is_development:
                logger.info(f"🔧 Development mode - logs: {settings.log_dir}")

            # Set cache type in app state for WebhookController detection
            app.state.wappa_cache_type = self.cache_type.value
            logger.debug(f"💾 Set app.state.wappa_cache_type = {self.cache_type.value}")

            # Create persistent HTTP session with optimized connection pooling
            logger.info("🌐 Creating persistent HTTP session...")
            connector = aiohttp.TCPConnector(
                limit=100,  # Max connections
                keepalive_timeout=30,  # Keep alive timeout
                enable_cleanup_closed=True,  # Auto cleanup closed connections
            )
            session = aiohttp.ClientSession(
                connector=connector, timeout=aiohttp.ClientTimeout(total=30)
            )
            app.state.http_session = session
            logger.info(
                "✅ Persistent HTTP session created - connections: 100, keepalive: 30s"
            )

            # Log available endpoints
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

            # Generate and display WhatsApp webhook URL
            await self._display_webhook_urls(logger, base_url)

            logger.info("✅ Wappa core startup completed successfully")

        except Exception as e:
            if logger:
                logger.error(f"❌ Error during Wappa core startup: {e}", exc_info=True)
            else:
                print(f"💥 Critical error during logging setup: {e}")
            raise

    async def _core_shutdown(self, app: FastAPI) -> None:
        """
        Core Wappa shutdown functionality.

        This hook runs last (priority 90) to clean up core resources after
        all other plugins have shut down:
        - Close HTTP session
        - Final logging

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        logger.info("🛑 Starting Wappa core shutdown...")

        try:
            # Close HTTP session and connector if it exists
            if hasattr(app.state, "http_session"):
                await app.state.http_session.close()
                logger.info("🌐 Persistent HTTP session closed cleanly")

            # Clear cache type from app state
            if hasattr(app.state, "wappa_cache_type"):
                del app.state.wappa_cache_type
                logger.debug("💾 Cache type cleared from app state")

            logger.info("✅ Wappa core shutdown completed")

        except Exception as e:
            logger.error(f"❌ Error during Wappa core shutdown: {e}", exc_info=True)

    async def _display_webhook_urls(self, logger, base_url: str) -> None:
        """
        Generate and display WhatsApp webhook URLs for user convenience.

        Args:
            logger: Logger instance
            base_url: Base URL for the application
        """
        try:
            # Import here to avoid circular imports during startup
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
        """
        Get the configured cache type.

        Returns:
            CacheType enum value
        """
        return self.cache_type

    def set_cache_type(self, cache_type: CacheType) -> None:
        """
        Update the cache type configuration.

        Args:
            cache_type: New cache type to use

        Note:
            This should be called before the application starts, as the
            cache type is set in app state during startup.
        """
        self.cache_type = cache_type
