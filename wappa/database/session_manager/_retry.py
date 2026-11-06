"""Transient-error classification, backoff and initialization retry."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from wappa.database.session_manager._base import _ManagerBase
from wappa.resilience import is_transient_db_error

logger = logging.getLogger("wappa.database.session_manager")


class _RetryMixin(_ManagerBase):
    """Backoff math and the startup health check with retry."""

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient and should be retried.

        Args:
            error: Exception to check

        Returns:
            True if error is likely transient and retryable

        Note:
            Classification lives in ``wappa.resilience`` so the session
            manager, transport adapters, and host-owned retry decorators all
            agree on what "transient" means. Pool checkout timeouts are
            excluded there: the pool is already drained, so retrying just
            parks the request and saturates the pooler further.
        """
        return is_transient_db_error(error)

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (2**attempt)
        # Add jitter (0.5x to 1.5x)
        jitter = 0.5 + random.random()
        delay *= jitter
        return cast(float, min(delay, self.max_delay))

    async def _initialize_with_retry(
        self,
        engine: AsyncEngine,
        is_primary: bool = True,
        replica_index: int | None = None,
    ) -> bool:
        """
        Perform health check with retry logic during initialization.

        Uses exponential backoff for transient failures like DNS resolution,
        network timeouts, and temporary connection issues that commonly occur
        during container orchestration (Docker Compose, Kubernetes).

        Args:
            engine: AsyncEngine to health check
            is_primary: Whether this is the primary write database
            replica_index: Index of read replica (if applicable)

        Returns:
            True if health check succeeds, False after max retries
        """
        if not is_primary and replica_index is None:
            raise ValueError("replica_index is required for a read replica")
        if is_primary:
            db_type = "primary database"
        else:
            assert replica_index is not None
            db_type = f"read replica {replica_index + 1}"
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # Perform health check on specific engine
                async with engine.begin() as conn:
                    result = await conn.execute(text("SELECT 1"))
                    if result.scalar() == 1:
                        if attempt > 0:
                            logger.info(
                                "%s connection established on attempt %d/%d",
                                db_type.capitalize(),
                                attempt + 1,
                                self.max_retries,
                            )
                        return True

                # Health check returned unexpected result
                logger.warning(
                    "%s health check returned unexpected result (attempt %d/%d)",
                    db_type.capitalize(),
                    attempt + 1,
                    self.max_retries,
                )

                # Treat unexpected result as transient
                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.info("Retrying %s in %.2fs...", db_type, delay)
                    await asyncio.sleep(delay)

            except Exception as e:
                last_exception = e

                # Check if error is transient
                if not self._is_transient_error(e):
                    logger.error("Non-transient error connecting to %s: %s", db_type, e)
                    return False

                # Log and retry for transient errors
                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        "%s connection failed (attempt %d/%d): %s. Retrying in %.2fs...",
                        db_type.capitalize(),
                        attempt + 1,
                        self.max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        if last_exception:
            logger.error(
                "%s connection failed after %d attempts: %s",
                db_type.capitalize(),
                self.max_retries,
                last_exception,
            )

        return False
