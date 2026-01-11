"""
Reconnection Strategy - Manages reconnection logic with exponential backoff.

Single Responsibility: Handle reconnection attempts with configurable backoff strategy.
"""

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReconnectionConfig:
    """Configuration for reconnection behavior."""

    base_delay: int = 10
    max_delay: int = 300
    max_attempts: int | None = None


@dataclass
class ReconnectionStrategy:
    """
    Manages reconnection attempts with exponential backoff.

    Responsibilities:
        - Track reconnection attempt count
        - Calculate exponential backoff delays
        - Enforce maximum attempt limits
        - Provide async wait between attempts

    Algorithm:
        wait_time = min(base_delay * (2 ^ (attempt - 1)), max_delay)

    Example progression (base_delay=10, max_delay=300):
        Attempt 1: 10s
        Attempt 2: 20s
        Attempt 3: 40s
        Attempt 4: 80s
        Attempt 5: 160s
        Attempt 6+: 300s (capped)

    Usage:
        strategy = ReconnectionStrategy(config=ReconnectionConfig(base_delay=10))

        while strategy.should_retry():
            try:
                await connect()
                strategy.reset()
            except ConnectionError:
                strategy.record_failure()
                await strategy.wait()
    """

    config: ReconnectionConfig = field(default_factory=ReconnectionConfig)
    _attempt_count: int = field(default=0, init=False)

    @property
    def attempt_count(self) -> int:
        """Current reconnection attempt count."""
        return self._attempt_count

    def record_failure(self) -> None:
        """
        Record a connection failure.

        Increments attempt counter for backoff calculation.
        """
        self._attempt_count += 1
        logger.error(
            "Connection failure recorded (attempt %d)",
            self._attempt_count,
        )

    def reset(self) -> None:
        """
        Reset attempt counter on successful connection.

        Should be called after connection is established.
        """
        if self._attempt_count > 0:
            logger.debug(
                "Reconnection successful after %d attempts, resetting counter",
                self._attempt_count,
            )
        self._attempt_count = 0

    def should_retry(self) -> bool:
        """
        Check if another reconnection attempt should be made.

        Returns:
            True if max_attempts not set or not reached, False otherwise
        """
        if self.config.max_attempts is None:
            return True
        return self._attempt_count < self.config.max_attempts

    def calculate_delay(self) -> int:
        """
        Calculate delay for next reconnection attempt.

        Uses exponential backoff capped at max_delay.

        Returns:
            Delay in seconds
        """
        if self._attempt_count == 0:
            return self.config.base_delay

        exponential = self.config.base_delay * (2 ** (self._attempt_count - 1))
        return min(exponential, self.config.max_delay)

    async def wait(self) -> None:
        """
        Wait before next reconnection attempt.

        Logs the wait time and sleeps asynchronously.
        """
        delay = self.calculate_delay()
        logger.info("Reconnecting in %d seconds...", delay)
        await asyncio.sleep(delay)

    def get_status(self) -> dict:
        """
        Get current reconnection status.

        Returns:
            Dict with attempt count, max attempts, and next delay
        """
        return {
            "attempt_count": self._attempt_count,
            "max_attempts": self.config.max_attempts,
            "next_delay": self.calculate_delay(),
            "should_retry": self.should_retry(),
        }
