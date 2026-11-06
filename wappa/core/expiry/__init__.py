"""Redis Expiry Keys as a trigger source of the scheduled lane.

An expired key becomes a ``ScheduledEvent`` delivered to
``WappaEventHandler.process_scheduled_event``. Compose it with
``SchedulingPlugin(redis_expiry=True)``; arm and cancel triggers through
``cache_factory.create_expiry_cache()``. Redis only: memory and JSON caches have
no timer engine.
"""

from .connection import ConnectionConfig, RedisConnection, RedisConnectionManager
from .dispatcher import ExpiryDispatcher, ExpirySubjectBinding
from .listener import run_expiry_listener
from .parser import ExpiryNotification, parse_expiry_notification
from .reconnection import ReconnectionConfig, ReconnectionStrategy

__all__ = [
    "ConnectionConfig",
    "ExpiryDispatcher",
    "ExpiryNotification",
    "ExpirySubjectBinding",
    "ReconnectionConfig",
    "ReconnectionStrategy",
    "RedisConnection",
    "RedisConnectionManager",
    "parse_expiry_notification",
    "run_expiry_listener",
]
