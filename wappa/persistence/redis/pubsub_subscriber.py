"""
Redis PubSub subscriber utilities for frontend integration.

Provides async helpers for subscribing to Wappa notifications in
Reflex-based frontend applications.

Channel Pattern: wappa:notify:{tenant}:{user_id}:{event_type}

Usage:
    from redis.asyncio import Redis
    from wappa.persistence.redis import subscribe, build_pattern

    redis = Redis.from_url("redis://localhost:6379")
    pattern = build_pattern("my_tenant", event_type="incoming_message")

    async for notification in subscribe(redis, patterns=[pattern]):
        print(f"Received: {notification.event} for {notification.user_id}")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from .redis_handler.utils.key_factory import KeyFactory

logger = logging.getLogger("PubSubSubscriber")

# Shared key factory for channel building
_key_factory = KeyFactory()


@dataclass
class Notification:
    """Parsed notification from PubSub channel."""

    event: str
    tenant: str
    user_id: str
    platform: str
    data: dict[str, Any]
    timestamp: str
    channel: str
    version: str = "1"


async def subscribe(
    redis: Redis,
    channels: list[str] | None = None,
    patterns: list[str] | None = None,
) -> AsyncIterator[Notification]:
    """
    Subscribe to PubSub channels and yield notifications.

    Args:
        redis: Redis client connection
        channels: Exact channel names for SUBSCRIBE
        patterns: Channel patterns for PSUBSCRIBE (supports * wildcards)

    Yields:
        Notification objects for each received message
    """
    if not channels and not patterns:
        raise ValueError("At least one channel or pattern must be provided")

    pubsub: PubSub = redis.pubsub()

    try:
        if channels:
            await pubsub.subscribe(*channels)
            logger.debug(f"Subscribed to channels: {channels}")

        if patterns:
            await pubsub.psubscribe(*patterns)
            logger.debug(f"Subscribed to patterns: {patterns}")

        async for message in pubsub.listen():
            if message["type"] not in ("message", "pmessage"):
                continue

            try:
                payload = json.loads(message["data"])
                channel_raw = message.get("channel", "")
                channel_name = (
                    channel_raw.decode("utf-8")
                    if isinstance(channel_raw, bytes)
                    else str(channel_raw)
                )

                yield Notification(
                    event=payload.get("event", "unknown"),
                    tenant=payload.get("tenant", ""),
                    user_id=payload.get("user_id", ""),
                    platform=payload.get("platform", "whatsapp"),
                    data=payload.get("data", {}),
                    timestamp=payload.get("timestamp", ""),
                    channel=channel_name,
                    version=payload.get("v", "1"),
                )

            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in PubSub message: {e}")
            except Exception as e:
                logger.error(f"Error processing PubSub message: {e}")

    except asyncio.CancelledError:
        logger.info("PubSub subscriber cancelled")
        raise
    finally:
        await pubsub.close()


def build_channel(tenant: str, user_id: str, event_type: str) -> str:
    """
    Build exact channel name for SUBSCRIBE.

    Args:
        tenant: Tenant identifier
        user_id: User/phone identifier
        event_type: Event type (incoming_message, outgoing_message, bot_reply, status_change)

    Returns:
        Channel name like "wappa:notify:tenant:user:event"
    """
    return _key_factory.channel(tenant, user_id, event_type)


def build_pattern(
    tenant: str,
    user_id: str = "*",
    event_type: str = "*",
) -> str:
    """
    Build channel pattern for PSUBSCRIBE with wildcards.

    Args:
        tenant: Tenant identifier (required)
        user_id: User/phone identifier (default "*" for all users)
        event_type: Event type (default "*" for all events)

    Returns:
        Pattern like "wappa:notify:tenant:*:*"

    Examples:
        # All events for a tenant
        build_pattern("my_tenant")

        # All events for specific user
        build_pattern("my_tenant", "5511999887766")

        # Only incoming messages for all users
        build_pattern("my_tenant", event_type="incoming_message")
    """
    return _key_factory.channel_pattern(tenant, user_id, event_type)


async def listen_once(
    redis: Redis,
    channels: list[str] | None = None,
    patterns: list[str] | None = None,
    timeout: float = 30.0,
) -> Notification | None:
    """Wait for a single notification with timeout."""
    try:
        async with asyncio.timeout(timeout):
            async for notif in subscribe(redis, channels, patterns):
                return notif
    except TimeoutError:
        logger.debug(f"listen_once timed out after {timeout}s")
        return None


class NotificationBuffer:
    """Buffer for collecting notifications in batch scenarios."""

    def __init__(self, max_size: int = 100, max_wait: float = 5.0):
        self.max_size = max_size
        self.max_wait = max_wait
        self._buffer: list[Notification] = []
        self._first_add_time: float | None = None

    def add(self, notification: Notification) -> None:
        """Add notification to buffer."""
        if not self._buffer:
            self._first_add_time = time.time()
        self._buffer.append(notification)

    def is_ready(self) -> bool:
        """Check if buffer should be flushed."""
        if len(self._buffer) >= self.max_size:
            return True
        return bool(
            self._first_add_time
            and (time.time() - self._first_add_time) >= self.max_wait
        )

    def flush(self) -> list[Notification]:
        """Flush and return all buffered notifications."""
        notifications = self._buffer
        self._buffer = []
        self._first_add_time = None
        return notifications

    def __len__(self) -> int:
        return len(self._buffer)
