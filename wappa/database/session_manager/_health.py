"""Health probes and read-only status accessors."""

from __future__ import annotations

import logging
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from wappa.database.session_manager._base import _ManagerBase
from wappa.database.session_manager._metrics import _PoolMetrics

logger = logging.getLogger("wappa.database.session_manager")


class _HealthMixin(_ManagerBase):
    """Health check, health status and initialization accessors."""

    async def health_check(self) -> bool:
        """
        Perform health check on primary database.

        Returns:
            True if database is healthy and responsive
        """
        if not self._write_engine:
            return False

        try:
            async with self._write_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            return False

    def get_health_status(self) -> dict:
        """
        Get detailed health status information.

        Returns:
            Dictionary with health status details
        """
        if not self._write_engine:
            return {
                "healthy": False,
                "initialized": self._initialized,
                "error": "Engine not initialized",
            }

        pool = cast(_PoolMetrics, self._write_engine.pool)

        return {
            "healthy": self._initialized,
            "initialized": self._initialized,
            "pool_size": pool.size(),
            "pool_checked_in": pool.checkedin(),
            "pool_checked_out": pool.checkedout(),
            "pool_overflow": pool.overflow(),
            "read_replicas": len(self._read_engines),
            "auto_commit": self.auto_commit,
            "max_retries": self.max_retries,
        }

    def is_initialized(self) -> bool:
        """Check if session manager is initialized."""
        return self._initialized

    @property
    def write_engine(self) -> AsyncEngine | None:
        """Get the write engine (for advanced use cases like schema creation)."""
        return self._write_engine
