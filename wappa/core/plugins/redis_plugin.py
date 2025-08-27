"""
Redis Plugin

Plugin for integrating Redis caching functionality with the Wappa framework.
Uses the Wappa library's own RedisManager for clean dependency management.
"""

from typing import Any, TYPE_CHECKING

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

    def __init__(
        self,
        max_connections: int = None,
        **redis_config: Any
    ):
        """
        Initialize Redis plugin.
        
        Redis URL is automatically loaded from settings.redis_url.
        
        Args:
            max_connections: Max Redis connections (defaults to settings.redis_max_connections)
            **redis_config: Additional Redis configuration options
        """
        self.max_connections = max_connections
        self.redis_config = redis_config
        self._redis_manager = None

    async def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the Redis plugin with WappaBuilder.
        
        Redis plugin doesn't need to configure middleware/routes,
        it manages its own lifecycle through startup/shutdown.
        
        Args:
            builder: WappaBuilder instance
        """
        # Redis plugin doesn't need to configure middleware/routes
        pass

    async def startup(self, app: "FastAPI") -> None:
        """
        Initialize Redis during application startup.
        
        Uses Wappa's own RedisManager for clean dependency management
        without relying on external app infrastructure.
        
        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        
        try:
            # Store reference to RedisManager class
            self._redis_manager = RedisManager
            
            # Initialize Redis using Wappa's RedisManager
            logger.info("Initializing Redis using Wappa's RedisManager...")
            
            # Initialize Redis pools with custom configuration if provided
            # RedisManager.initialize() will use settings.redis_url if redis_url is None
            await RedisManager.initialize(
                redis_url=None,  # Use settings.redis_url automatically
                max_connections=self.max_connections
            )
            
            # Store RedisManager reference in app state for user access
            app.state.redis_manager = RedisManager
            
            # Get health status for logging
            health_status = await RedisManager.get_health_status()
            healthy_pools = [
                alias for alias, status in health_status.get('pools', {}).items()
                if status.get('status') == 'healthy'
            ]
            
            logger.info(
                f"Redis plugin initialized successfully - "
                f"Healthy pools: {len(healthy_pools)}, "
                f"Total pools: {len(health_status.get('pools', {}))}"
            )
            
            # Log pool information for debugging
            pool_info = RedisManager.get_pool_info()
            logger.debug(f"Available Redis pools: {pool_info}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis plugin: {e}", exc_info=True)
            raise RuntimeError(f"Redis plugin startup failed: {e}") from e

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Clean up Redis resources during application shutdown.
        
        Uses the existing RedisManager.cleanup() method to ensure
        proper resource cleanup matching the original pattern.
        
        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()
        
        try:
            if self._redis_manager and self._redis_manager.is_initialized():
                logger.debug("Cleaning up Redis connections...")
                await self._redis_manager.cleanup()
                logger.info("Redis plugin shutdown successfully")
            
            # Clean up app state
            if hasattr(app.state, 'redis_manager'):
                del app.state.redis_manager
                
        except Exception as e:
            logger.error(f"Error during Redis plugin shutdown: {e}", exc_info=True)

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
        if not self._redis_manager or not self._redis_manager.is_initialized():
            return {
                'healthy': False,
                'error': 'Redis manager not initialized',
                'initialized': False,
            }
        
        try:
            health_status = await self._redis_manager.get_health_status()
            return {
                'healthy': health_status.get('initialized', False),
                'plugin': 'RedisPlugin',
                **health_status,
            }
        except Exception as e:
            return {
                'healthy': False,
                'error': str(e),
                'plugin': 'RedisPlugin',
            }