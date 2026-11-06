"""
Expiry Listener - Redis KEYSPACE notification listener for expiry events.

Components:
- RedisConnectionManager: Connection lifecycle
- parse_expiry_notification: Key parsing
- ExpiryDispatcher: Adapts notifications to the scheduled-event path
- ReconnectionStrategy: Backoff logic
"""

from __future__ import annotations

import asyncio
import logging

from .connection import ConnectionConfig, RedisConnectionManager
from .dispatcher import ExpiryDispatcher
from .parser import parse_expiry_notification
from .reconnection import ReconnectionConfig, ReconnectionStrategy

logger = logging.getLogger(__name__)


async def run_expiry_listener(
    *,
    dispatcher: ExpiryDispatcher,
    alias: str = "expiry",
    reconnect_delay: int = 10,
    max_reconnect_attempts: int | None = None,
) -> None:
    """
    Run long-running expiry listener task.

    Subscribes to Redis KEYSPACE notifications for expired keys and hands each
    valid Expiry Key to the dispatcher.

    Args:
        dispatcher: Adapts each notification to the scheduled-event path
        alias: Redis pool alias (default: "expiry")
        reconnect_delay: Seconds to wait before reconnecting on error
        max_reconnect_attempts: Max reconnection attempts (None = infinite)

    Lifecycle:
        1. Get Redis client for expiry pool
        2. Enable keyspace notifications
        3. Subscribe to __keyevent@{db}__:expired channel
        4. Listen for expiry events
        5. Parse expired keys
        6. Dispatch them asynchronously
        7. Reconnect on connection loss with exponential backoff
    """
    # Initialize components with configuration
    connection_manager = RedisConnectionManager(config=ConnectionConfig(alias=alias))
    reconnection = ReconnectionStrategy(
        config=ReconnectionConfig(
            base_delay=reconnect_delay,
            max_attempts=max_reconnect_attempts,
        )
    )

    logger.info("Starting Redis expiry listener (alias=%s)", alias)

    while reconnection.should_retry():
        try:
            await _run_listener_loop(
                connection_manager=connection_manager,
                dispatcher=dispatcher,
            )
            reconnection.reset()

        except asyncio.CancelledError:
            logger.info("Expiry listener cancelled, shutting down")
            await connection_manager.disconnect()
            break

        except Exception as e:
            reconnection.record_failure()
            logger.error(
                "Expiry listener error (attempt %d): %s",
                reconnection.attempt_count,
                e,
                exc_info=True,
            )

            if not reconnection.should_retry():
                logger.critical(
                    "Max reconnection attempts reached (%d), exiting listener",
                    reconnection.config.max_attempts,
                )
                break

            await reconnection.wait()

    logger.info("Expiry listener terminated")


async def _run_listener_loop(
    *,
    connection_manager: RedisConnectionManager,
    dispatcher: ExpiryDispatcher,
) -> None:
    """
    Main event processing loop.

    Connects to Redis and processes expiry events until disconnection.

    Args:
        connection_manager: Manages Redis connection lifecycle
        dispatcher: Dispatches each parsed notification
    """
    connection = await connection_manager.connect()

    logger.info("Expiry listener active and listening")

    async for msg in connection.pubsub.listen():
        notification = parse_expiry_notification(msg)
        if notification is not None:
            dispatcher.dispatch(notification)


__all__ = [
    "run_expiry_listener",
]
