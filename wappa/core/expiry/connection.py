"""
Redis Connection Manager - Handles Redis connection lifecycle for expiry listener.

Single Responsibility: Redis connection setup, teardown, and keyspace notification config.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, cast

from ...persistence.redis.redis_client import PoolAlias, RedisClient

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from redis.asyncio.client import PubSub

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    """Configuration for Redis connection."""

    alias: str = "expiry"


@dataclass
class RedisConnectionManager:
    """
    Manages Redis connection lifecycle for expiry listener.

    Responsibilities:
        - Obtain Redis client from pool
        - Configure keyspace notifications
        - Create and manage PubSub subscription
        - Extract database index for channel construction

    Usage:
        manager = RedisConnectionManager(config=ConnectionConfig(alias="expiry"))
        async with manager.connect() as connection:
            async for msg in connection.pubsub.listen():
                # Process messages
                pass
    """

    config: ConnectionConfig = field(default_factory=ConnectionConfig)
    _redis: Optional["Redis"] = field(default=None, init=False, repr=False)
    _pubsub: Optional["PubSub"] = field(default=None, init=False, repr=False)
    _channel: str | None = field(default=None, init=False)

    async def connect(self) -> "RedisConnection":
        """
        Establish Redis connection and configure for expiry events.

        Returns:
            RedisConnection context with active PubSub subscription

        Raises:
            ConnectionError: If Redis connection fails
        """
        self._redis = await RedisClient.get(cast(PoolAlias, self.config.alias))

        db_index = self._extract_db_index()
        self._channel = f"__keyevent@{db_index}__:expired"

        logger.info(
            "Expiry listener connecting to Redis (db=%d, channel=%s)",
            db_index,
            self._channel,
        )

        await self._configure_keyspace_notifications()

        self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self._channel)

        logger.info("Expiry listener active and listening")

        return RedisConnection(
            redis=self._redis,
            pubsub=self._pubsub,
            channel=self._channel,
            db_index=db_index,
        )

    async def disconnect(self) -> None:
        """
        Clean up Redis connection resources.

        Unsubscribes from PubSub and closes connection.
        """
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception as e:
                logger.warning("Error closing PubSub: %s", e)
            self._pubsub = None

        self._redis = None
        self._channel = None
        logger.debug("Redis connection resources cleaned up")

    def _extract_db_index(self) -> int:
        """Extract database number from Redis connection pool."""
        if not self._redis:
            return 0
        return self._redis.connection_pool.connection_kwargs.get("db", 0)

    async def _configure_keyspace_notifications(self) -> None:
        """
        Enable Redis keyspace notifications for expiry events.

        Sets: notify-keyspace-events = Ex
        - E: Enable keyspace notifications
        - x: Enable expiry event notifications
        """
        if not self._redis:
            return

        try:
            await self._redis.config_set("notify-keyspace-events", "Ex")
            logger.info("Redis keyspace notifications enabled (Ex)")
        except Exception as e:
            logger.warning(
                "Failed to enable keyspace notifications: %s. "
                "Ensure Redis config has notify-keyspace-events=Ex",
                e,
            )


@dataclass
class RedisConnection:
    """
    Active Redis connection context.

    Contains all resources needed for listening to expiry events.
    """

    redis: "Redis"
    pubsub: "PubSub"
    channel: str
    db_index: int
