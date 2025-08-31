"""
Redis Plugin

Plugin for integrating Redis caching functionality with the Wappa framework.
Uses the Wappa library's own RedisManager for clean dependency management.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger
from ...persistence.redis.redis_manager import RedisManager

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ...core.factory.wappa_builder import WappaBuilder


class RedisPlugin:
    """
    Redis plugin for Wappa applications.

    This plugin integrates Redis caching functionality using Wappa's own
    RedisManager and ICacheFactory pattern. It automatically uses settings.redis_url
    and provides clean dependency injection through the event handler cache_factory.

    Example:
        # Basic usage (uses settings.redis_url automatically)
        redis_plugin = RedisPlugin()

        # With custom max connections
        redis_plugin = RedisPlugin(max_connections=100)

        builder.add_plugin(redis_plugin)

        # Access in event handlers through ICacheFactory
        user_cache = self.cache_factory.create_user_cache(tenant_id, user_id)
        await user_cache.set('key', 'value')
    """

    def __init__(self, max_connections: int | None = None, **redis_config: Any):
        """
        Initialize Redis plugin.

        Redis URL is automatically loaded from settings.redis_url.
        The plugin uses hook-based architecture - Redis initialization
        happens during the startup hook, not during plugin construction.

        Args:
            max_connections: Max Redis connections (defaults to settings.redis_max_connections)
            **redis_config: Additional Redis configuration options
        """
        self.max_connections = max_connections
        self.redis_config = redis_config

    def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure Redis plugin with WappaBuilder using hook-based architecture.

        Registers Redis initialization and cleanup as hooks with the builder's
        unified lifespan management system. This ensures Redis starts after
        core Wappa functionality (logging) and shuts down before core cleanup.

        Args:
            builder: WappaBuilder instance to register hooks with
        """
        # Register Redis lifecycle hooks with appropriate priorities
        # Priority 20: After core startup (10) but before user hooks (50)
        builder.add_startup_hook(self._redis_startup, priority=20)
        builder.add_shutdown_hook(self._redis_shutdown, priority=20)

        logger = get_app_logger()
        logger.debug("🔧 RedisPlugin configured - registered startup/shutdown hooks")

    async def startup(self, app: "FastAPI") -> None:
        """
        Plugin startup method required by WappaPlugin protocol.

        Delegates to _redis_startup hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._redis_startup(app)

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Plugin shutdown method required by WappaPlugin protocol.

        Delegates to _redis_shutdown hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._redis_shutdown(app)

    async def _redis_startup(self, app: "FastAPI") -> None:
        """
        Redis initialization hook - runs after core Wappa startup.

        This hook is registered with priority 20, ensuring it runs after
        core Wappa functionality (priority 10) has initialized logging
        and other essential services.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Import settings for explicit configuration
            from ...core.config.settings import settings

            # Use explicit settings - more readable than None
            redis_url = settings.redis_url
            max_conn = self.max_connections or settings.redis_max_connections

            logger.info("=== REDIS CACHE INITIALIZATION ===")
            logger.info(f"🔴 Redis URL: {redis_url} (max_connections: {max_conn})")

            # Initialize Redis pools with explicit settings
            await RedisManager.initialize(
                redis_url=redis_url,  # Explicit, not None - more readable
                max_connections=max_conn,
            )

            # Store RedisManager reference in app state for cache factory access
            app.state.redis_manager = RedisManager

            # Get detailed health status for confirmation
            health_status = await RedisManager.get_health_status()
            healthy_pools = [
                alias
                for alias, status in health_status.get("pools", {}).items()
                if status.get("status") == "healthy"
            ]

            # Success confirmation with pool details
            pool_info = RedisManager.get_pool_info()
            logger.info(
                f"✅ Redis startup completed! "
                f"Healthy pools: {len(healthy_pools)}/{len(pool_info)} "
                f"({', '.join(f'{alias}:db{db}' for alias, db in pool_info.items())})"
            )
            logger.info("===============================")

            # Debug detailed pool information
            logger.debug(f"Redis pool health details: {health_status}")

        except Exception as e:
            logger.error(f"❌ Redis startup hook failed: {e}", exc_info=True)
            raise RuntimeError(f"RedisPlugin startup hook failed: {e}") from e

    async def _redis_shutdown(self, app: "FastAPI") -> None:
        """
        Redis cleanup hook - runs before core Wappa shutdown.

        This hook is registered with priority 20, ensuring it runs before
        core Wappa cleanup (priority 90) to properly close Redis connections
        while logging is still available.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Clean up Redis connections if initialized
            if hasattr(app.state, "redis_manager") and RedisManager.is_initialized():
                logger.info("=== REDIS CACHE SHUTDOWN ===")
                logger.debug("🔴 Cleaning up Redis connections...")
                await RedisManager.cleanup()
                logger.info("✅ Redis shutdown completed")
                logger.info("==============================")

            # Clean up app state
            if hasattr(app.state, "redis_manager"):
                del app.state.redis_manager
                logger.debug("🧹 Redis manager removed from app state")

        except Exception as e:
            # Don't re-raise in shutdown - log and continue
            logger.error(f"❌ Error during Redis shutdown hook: {e}", exc_info=True)

    async def get_health_status(self, app: "FastAPI") -> dict[str, Any]:
        """
        Get Redis health status for monitoring.

        Uses the existing RedisManager.get_health_status() method
        to provide consistent health reporting.

        Args:
            app: FastAPI application instance

        Returns:
            Dictionary with Redis health information
        """
        if not RedisManager.is_initialized():
            return {
                "healthy": False,
                "error": "Redis manager not initialized",
                "initialized": False,
                "plugin": "RedisPlugin",
            }

        try:
            health_status = await RedisManager.get_health_status()
            return {
                "healthy": health_status.get("initialized", False),
                "plugin": "RedisPlugin",
                **health_status,
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "plugin": "RedisPlugin",
            }
