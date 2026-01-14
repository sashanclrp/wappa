"""
ExpiryPlugin - Redis Expiry Action Lifecycle Management

Plugin for managing the Redis expiry action listener lifecycle in Wappa applications.
Handles starting and stopping the background listener task that processes expired keys.
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from ...persistence.redis.redis_manager import RedisManager
from ..expiry.listener import run_expiry_listener

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ..factory.wappa_builder import WappaBuilder

logger = logging.getLogger(__name__)


class ExpiryPlugin:
    """
    Plugin for Redis expiry action lifecycle management.

    Responsibilities:
    - Start expiry listener task on application startup
    - Store task reference in app state
    - Cancel listener task on application shutdown
    - Verify Redis expiry pool availability

    Usage:
        # Basic usage (uses default settings)
        expiry_plugin = ExpiryPlugin()
        builder.add_plugin(expiry_plugin)

        # With custom settings
        expiry_plugin = ExpiryPlugin(
            alias="expiry",
            reconnect_delay=10,
            max_reconnect_attempts=None  # Infinite retries
        )
        builder.add_plugin(expiry_plugin)

    Example:
        from wappa import WappaBuilder, ExpiryPlugin

        app = (WappaBuilder()
               .with_whatsapp(token="...", phone_id="...")
               .with_redis_cache("redis://localhost:6379")
               .add_plugin(ExpiryPlugin())
               .build())
    """

    def __init__(
        self,
        *,
        alias: str = "expiry",
        reconnect_delay: int = 10,
        max_reconnect_attempts: int | None = None,
    ):
        """
        Initialize expiry plugin.

        Args:
            alias: Redis pool alias for expiry triggers (default: "expiry")
            reconnect_delay: Seconds to wait before reconnecting on error
            max_reconnect_attempts: Max reconnection attempts (None = infinite)
        """
        self.alias = alias
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self._listener_task: asyncio.Task | None = None

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure plugin with Wappa builder.

        Registers startup and shutdown hooks with priority 25 (after Redis at 20).

        Args:
            builder: WappaBuilder instance to register hooks with
        """
        # Register lifecycle hooks with priority 25 (after Redis at 20)
        builder.add_startup_hook(self._startup_hook, priority=25)
        builder.add_shutdown_hook(self._shutdown_hook, priority=25)

        logger.debug("🔧 ExpiryPlugin configured - registered startup/shutdown hooks")

    async def startup(self, app: "FastAPI") -> None:
        """
        Plugin startup method required by WappaPlugin protocol.

        Delegates to _startup_hook for actual implementation.

        Args:
            app: FastAPI application instance
        """
        await self._startup_hook(app)

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Plugin shutdown method required by WappaPlugin protocol.

        Delegates to _shutdown_hook for actual implementation.

        Args:
            app: FastAPI application instance
        """
        await self._shutdown_hook(app)

    async def _startup_hook(self, app: "FastAPI") -> None:
        """
        Startup hook: Start expiry listener task.

        Steps:
        1. Verify Redis expiry pool is initialized
        2. Start listener as background task
        3. Store task reference in app state

        Args:
            app: FastAPI application instance
        """
        logger.info("=== EXPIRY ACTIONS INITIALIZATION ===")

        try:
            # Verify Redis is initialized
            if not RedisManager.is_initialized():
                logger.error(
                    "❌ Redis not initialized. ExpiryPlugin requires Redis. "
                    "Did you forget to add RedisPlugin?"
                )
                raise RuntimeError("ExpiryPlugin requires Redis to be initialized")

            # Verify expiry pool exists
            try:
                await RedisManager.get_client(self.alias)
                logger.info(f"✅ Redis expiry pool '{self.alias}' verified")
            except Exception as e:
                logger.error(
                    f"❌ Expiry pool '{self.alias}' not found. "
                    f"Ensure RedisClient has '{self.alias}' pool configured."
                )
                raise RuntimeError(f"Expiry pool not configured: {e}") from e

            # Start listener task
            logger.info(
                f"🔴 Starting expiry listener (alias={self.alias}, "
                f"reconnect_delay={self.reconnect_delay}s, "
                f"max_attempts={self.max_reconnect_attempts or 'infinite'})"
            )

            self._listener_task = asyncio.create_task(
                run_expiry_listener(
                    alias=self.alias,
                    reconnect_delay=self.reconnect_delay,
                    max_reconnect_attempts=self.max_reconnect_attempts,
                ),
                name="expiry_listener",
            )

            # Store in app state for access/monitoring
            app.state.expiry_listener_task = self._listener_task

            # Store app reference globally for expiry handlers to access HTTP session
            from ..expiry.listener import set_fastapi_app

            set_fastapi_app(app)

            logger.info("✅ ExpiryPlugin startup completed")
            logger.info("====================================")

        except Exception as e:
            logger.error(f"❌ ExpiryPlugin startup hook failed: {e}", exc_info=True)
            raise RuntimeError(f"ExpiryPlugin startup hook failed: {e}") from e

    async def _shutdown_hook(self, app: "FastAPI") -> None:
        """
        Shutdown hook: Cancel listener task gracefully.

        Steps:
        1. Cancel listener task
        2. Wait for task to complete (max 5 seconds)
        3. Log shutdown completion

        Args:
            app: FastAPI application instance
        """
        logger.info("=== EXPIRY ACTIONS SHUTDOWN ===")

        try:
            if self._listener_task and not self._listener_task.done():
                logger.debug("🔴 Cancelling expiry listener task...")
                self._listener_task.cancel()

                try:
                    # Wait for graceful shutdown (max 5 seconds)
                    await asyncio.wait_for(
                        asyncio.shield(self._listener_task), timeout=5.0
                    )
                    logger.info("✅ Expiry listener cancelled successfully")
                except TimeoutError:
                    logger.warning("⚠️ Expiry listener did not shut down gracefully")
                except asyncio.CancelledError:
                    logger.info("✅ Expiry listener cancelled")

            # Clean up app state
            if hasattr(app.state, "expiry_listener_task"):
                del app.state.expiry_listener_task
                logger.debug("🧹 Expiry listener task removed from app state")

            logger.info("✅ ExpiryPlugin shutdown completed")
            logger.info("==============================")

        except Exception as e:
            # Don't re-raise in shutdown - log and continue
            logger.error(
                f"❌ Error during ExpiryPlugin shutdown hook: {e}", exc_info=True
            )

    @staticmethod
    def get_listener_task(app: "FastAPI") -> asyncio.Task | None:
        """
        Get listener task from app state (for monitoring).

        Args:
            app: FastAPI application instance

        Returns:
            Listener task or None if not available
        """
        return getattr(app.state, "expiry_listener_task", None)

    @staticmethod
    def is_listener_running(app: "FastAPI") -> bool:
        """
        Check if listener is running.

        Args:
            app: FastAPI application instance

        Returns:
            True if listener is running, False otherwise
        """
        task = ExpiryPlugin.get_listener_task(app)
        return task is not None and not task.done()
