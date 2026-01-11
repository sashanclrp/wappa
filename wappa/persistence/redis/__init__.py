"""
Redis Module

Provides Redis client functionality, operations, and lifecycle management.
Includes PubSub subscriber utilities for real-time notifications.
"""

from . import ops, redis_handler
from .pubsub_subscriber import (
    Notification,
    NotificationBuffer,
    build_channel,
    build_pattern,
    listen_once,
    subscribe,
)
from .redis_client import RedisClient
from .redis_manager import RedisManager

__all__ = [
    # Core Redis
    "RedisClient",
    "RedisManager",
    "ops",
    "redis_handler",
    # PubSub Subscriber Utilities
    "subscribe",
    "build_channel",
    "build_pattern",
    "listen_once",
    "Notification",
    "NotificationBuffer",
]
