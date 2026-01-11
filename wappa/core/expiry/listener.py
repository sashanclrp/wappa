"""
Expiry Listener - Redis KEYSPACE notification listener for expiry events.

Refactored for SOLID compliance:
- Single Responsibility: Orchestrates components, doesn't implement details
- Open/Closed: Components can be extended without modifying listener
- Dependency Inversion: Depends on abstractions (interfaces), not concretions

Components:
- RedisConnectionManager: Connection lifecycle
- ExpiryEventParser: Key parsing (delegates to registry.resolve)
- ExpiryDispatcher: Handler dispatch
- ReconnectionStrategy: Backoff logic
"""

import asyncio
import logging

from .app_context import get_fastapi_app, set_fastapi_app
from .connection import ConnectionConfig, RedisConnectionManager
from .dispatcher import ExpiryDispatcher
from .parser import ExpiryEventParser
from .reconnection import ReconnectionConfig, ReconnectionStrategy
from .registry import expiry_registry

logger = logging.getLogger(__name__)


async def run_expiry_listener(
    *,
    alias: str = "expiry",
    reconnect_delay: int = 10,
    max_reconnect_attempts: int | None = None,
) -> None:
    """
    Run long-running expiry listener task.

    Subscribes to Redis KEYSPACE notifications for expired keys
    and dispatches registered handlers asynchronously.

    Args:
        alias: Redis pool alias (default: "expiry")
        reconnect_delay: Seconds to wait before reconnecting on error
        max_reconnect_attempts: Max reconnection attempts (None = infinite)

    Lifecycle:
        1. Get Redis client for expiry pool
        2. Enable keyspace notifications
        3. Subscribe to __keyevent@{db}__:expired channel
        4. Listen for expiry events
        5. Parse expired keys via registry.resolve()
        6. Dispatch handlers asynchronously
        7. Reconnect on connection loss with exponential backoff

    Example:
        # Start as background task in main.py
        listener_task = asyncio.create_task(
            run_expiry_listener(alias="expiry"),
            name="expiry_listener"
        )
    """
    # Initialize components with configuration
    connection_manager = RedisConnectionManager(config=ConnectionConfig(alias=alias))
    parser = ExpiryEventParser(registry=expiry_registry)
    dispatcher = ExpiryDispatcher()
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
                parser=parser,
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
    parser: ExpiryEventParser,
    dispatcher: ExpiryDispatcher,
) -> None:
    """
    Main event processing loop.

    Connects to Redis and processes expiry events until disconnection.

    Args:
        connection_manager: Manages Redis connection lifecycle
        parser: Parses expiry events from messages
        dispatcher: Dispatches handlers for events
    """
    connection = await connection_manager.connect()

    logger.info("Expiry listener active and listening")

    async for msg in connection.pubsub.listen():
        event = parser.parse(msg)
        if event:
            dispatcher.dispatch(event)


# Re-export backward compatibility functions
__all__ = [
    "run_expiry_listener",
    "get_fastapi_app",
    "set_fastapi_app",
]
