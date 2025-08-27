"""
Redis Manager for Wappa application lifecycle management.

Wraps the Wappa RedisClient with application-specific initialization and cleanup.
Provides a clean interface for applications to manage Redis connections.
"""

import logging
from typing import Any

from ...core.config.settings import settings
from .redis_client import POOL_DB_MAPPING, RedisClient, PoolAlias

logger = logging.getLogger(__name__)


class RedisManager:
    """
    Application-level wrapper around the Wappa RedisClient.

    Handles lifecycle management, health monitoring, and provides
    a clean interface for applications to manage Redis connections.
    
    This manager follows the same patterns as the reference implementation
    but uses Wappa's own RedisClient instead of external dependencies.
    """

    _initialized: bool = False

    @classmethod
    async def initialize(
        cls, 
        redis_url: str|None = None, 
        max_connections: int|None = None
    ) -> None:
        """
        Initialize Redis pools using Wappa's RedisClient.

        Uses the existing multi-pool setup with proper configuration
        from application settings or provided parameters.
        
        Args:
            redis_url: Redis connection URL (defaults to settings.redis_url)
            max_connections: Max connections per pool (defaults to settings.redis_max_connections)
        """
        if cls._initialized:
            logger.info("Redis pools already initialized")
            return

        try:
            logger.info("Initializing Redis pools...")

            # Use provided parameters or fall back to settings
            url = redis_url or getattr(settings, 'redis_url', 'redis://localhost:6379')
            connections = max_connections or getattr(settings, 'redis_max_connections', 64)

            # Use Wappa's RedisClient.setup_single_url
            RedisClient.setup_single_url(
                base_url=url,
                max_connections=connections,
            )

            # Verify all pools are working
            await cls._verify_pools()

            cls._initialized = True
            logger.info("Redis pools initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Redis pools: {e}", exc_info=True)
            raise

    @classmethod
    async def _verify_pools(cls) -> None:
        """
        Health check all Redis pools.

        Ensures all expected pools are accessible and responding.
        """
        failed_pools = []

        for alias in POOL_DB_MAPPING.keys():
            pool_alias: PoolAlias = alias  # type: ignore
            try:
                redis = await RedisClient.get(pool_alias)
                await redis.ping()
                logger.debug(f"Redis pool '{alias}' health check passed")
            except Exception as e:
                logger.error(f"Redis pool '{alias}' health check failed: {e}")
                failed_pools.append(alias)

        if failed_pools:
            raise ConnectionError(f"Failed to connect to Redis pools: {failed_pools}")

    @classmethod
    async def get_health_status(cls) -> dict[str, Any]:
        """
        Get health status of all Redis pools.

        Returns detailed health information for monitoring.
        
        Returns:
            Dictionary containing initialization status and per-pool health info
        """
        health_status = {"initialized": cls._initialized, "pools": {}}

        if not cls._initialized:
            health_status["message"] = "Redis not initialized"
            return health_status

        for alias in POOL_DB_MAPPING.keys():
            pool_alias: PoolAlias = alias  # type: ignore
            try:
                redis = await RedisClient.get(pool_alias)
                await redis.ping()
                health_status["pools"][alias] = {
                    "status": "healthy",
                    "database": POOL_DB_MAPPING[alias],
                    "error": None,
                }
            except Exception as e:
                health_status["pools"][alias] = {
                    "status": "unhealthy",
                    "database": POOL_DB_MAPPING[alias],
                    "error": str(e),
                }

        return health_status

    @classmethod
    async def get_client(cls, alias: PoolAlias = "users"):
        """
        Get Redis client for specified pool.
        
        Args:
            alias: Pool alias ("users", "state_handler", "table")
            
        Returns:
            Redis client instance
            
        Raises:
            RuntimeError: If Redis not initialized
        """
        if not cls._initialized:
            raise RuntimeError("RedisManager not initialized. Call initialize() first.")
        
        return await RedisClient.get(alias)
        
        return await RedisClient.get(alias)

    @classmethod
    async def cleanup(cls) -> None:
        """
        Clean shutdown of all Redis pools.

        Should be called during application shutdown.
        """
        if not cls._initialized:
            logger.info("Redis pools not initialized, skipping cleanup")
            return

        try:
            logger.info("Shutting down Redis pools...")
            await RedisClient.close()
            cls._initialized = False
            logger.info("Redis pools shut down successfully")
        except Exception as e:
            logger.error(f"Error during Redis cleanup: {e}", exc_info=True)
            raise

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if Redis pools are initialized."""
        return cls._initialized

    @classmethod
    def get_pool_info(cls) -> dict[str, int]:
        """
        Get information about available Redis pools.
        
        Returns:
            Dictionary mapping pool aliases to database numbers
        """
        return POOL_DB_MAPPING.copy()