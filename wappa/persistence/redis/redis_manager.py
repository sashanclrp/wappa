"""
Redis Manager for Wappa application lifecycle management.

Wraps the Wappa RedisClient with application-specific initialization and cleanup.
Provides a clean interface for applications to manage Redis connections.
"""

import logging
from typing import Any

from ...core.config.settings import settings
from .redis_client import POOL_DB_MAPPING, PoolAlias, RedisClient

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
        cls, redis_url: str | None = None, max_connections: int | None = None
    ) -> None:
        """
        Initialize Redis pools with enhanced logging.

        Uses the existing multi-pool setup with proper configuration
        from application settings or provided parameters.

        Args:
            redis_url: Redis connection URL (defaults to settings.redis_url)
            max_connections: Max connections per pool (defaults to settings.redis_max_connections)
        """
        if cls._initialized:
            logger.info("Redis pools already initialized - skipping")
            return

        try:
            # Enhanced initialization logging
            url = redis_url or settings.redis_url
            connections = max_connections or settings.redis_max_connections

            logger.info(
                f"Setting up Redis pools from {url} (max_connections: {connections})"
            )

            # Use Wappa's RedisClient.setup_single_url
            RedisClient.setup_single_url(
                base_url=url,
                max_connections=connections,
            )

            # Verify all pools with detailed logging
            logger.info("Verifying Redis pool health...")
            await cls._verify_pools()

            cls._initialized = True

            # Success confirmation with pool details
            pool_count = len(POOL_DB_MAPPING)
            pool_details = ", ".join(
                f"{alias}:db{db}" for alias, db in POOL_DB_MAPPING.items()
            )
            logger.info(f"✅ Redis pools ready: {pool_count} pools ({pool_details})")

        except Exception as e:
            logger.error(f"❌ Redis pool initialization failed: {e}", exc_info=True)
            raise

    @classmethod
    async def _verify_pools(cls) -> None:
        """
        Health check all Redis pools with detailed logging.

        Ensures all expected pools are accessible and responding.
        """
        failed_pools = []
        successful_pools = []

        for alias in POOL_DB_MAPPING:
            pool_alias: PoolAlias = alias  # type: ignore
            try:
                redis = await RedisClient.get(pool_alias)
                await redis.ping()
                successful_pools.append(f"{alias}:db{POOL_DB_MAPPING[alias]}")
                logger.debug(
                    f"✅ Redis pool '{alias}' (db{POOL_DB_MAPPING[alias]}) health check passed"
                )
            except Exception as e:
                failed_pools.append(f"{alias}:db{POOL_DB_MAPPING[alias]}")
                logger.error(
                    f"❌ Redis pool '{alias}' (db{POOL_DB_MAPPING[alias]}) health check failed: {e}"
                )

        if failed_pools:
            raise ConnectionError(f"Failed Redis pools: {', '.join(failed_pools)}")

        logger.info(f"✅ All Redis pools healthy: {', '.join(successful_pools)}")

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

        for alias in POOL_DB_MAPPING:
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
