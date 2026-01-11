"""Redis PubSub publisher for real-time notifications."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ....domain.interfaces.pubsub_interface import IPubSubPublisher, PubSubEventType
from ..redis_client import RedisClient
from .utils.key_factory import KeyFactory

logger = logging.getLogger("RedisPubSub")


class RedisPubSubPublisher(BaseModel, IPubSubPublisher):
    """
    Redis PubSub publisher for real-time event notifications.

    Publishes lightweight notifications to channels. Actual data should be
    stored in UserCache - notifications just signal "something changed".

    Channel Pattern: wappa:notify:{tenant}:{user_id}:{event_type}
    """

    tenant: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    platform: str = Field(default="whatsapp")
    keys: KeyFactory = Field(default_factory=KeyFactory)

    model_config = {"arbitrary_types_allowed": True}

    def get_channel(self, event_type: PubSubEventType) -> str:
        """Get channel name for event type."""
        return self.keys.channel(self.tenant, self.user_id, event_type)

    async def publish(
        self,
        event_type: PubSubEventType,
        data: dict[str, Any],
    ) -> int:
        """
        Publish notification to channel.

        Returns the number of subscribers that received the message.
        """
        channel = self.get_channel(event_type)

        payload = {
            "event": event_type,
            "tenant": self.tenant,
            "user_id": self.user_id,
            "platform": self.platform,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
            "v": "1",
        }

        try:
            async with RedisClient.connection("users") as redis:
                subscribers = await redis.publish(channel, json.dumps(payload))
                logger.debug(
                    f"Published {event_type} to {channel}: {subscribers} subscriber(s)"
                )
                return subscribers

        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}", exc_info=True)
            return 0

    async def publish_batch(
        self,
        notifications: list[tuple[PubSubEventType, dict[str, Any]]],
    ) -> dict[str, int]:
        """Publish multiple notifications. Returns dict mapping channels to subscriber counts."""
        results = {}
        for event_type, data in notifications:
            channel = self.get_channel(event_type)
            subscribers = await self.publish(event_type, data)
            results[channel] = subscribers
        return results
