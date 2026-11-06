"""Typed attribute and helper declarations shared by the session-manager mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class _ManagerBase:
    """Shared state and cross-mixin helper signatures for ``PostgresSessionManager``."""

    write_url: str
    read_urls: list[str]
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    pool_pre_ping: bool
    echo: bool
    statement_cache_size: int | None
    command_timeout: float | None
    connect_timeout: float | None
    connect_max_retries: int
    max_retries: int
    base_delay: float
    max_delay: float
    auto_commit: bool
    _write_engine: AsyncEngine | None
    _read_engines: list[AsyncEngine]
    _write_session_maker: async_sessionmaker[AsyncSession] | None
    _read_session_makers: list[async_sessionmaker[AsyncSession]]
    _read_index: int
    _initialized: bool

    if TYPE_CHECKING:

        def _is_transient_error(self, error: Exception) -> bool: ...

        def _calculate_backoff(self, attempt: int) -> float: ...

        async def _initialize_with_retry(
            self,
            engine: AsyncEngine,
            is_primary: bool = True,
            replica_index: int | None = None,
        ) -> bool: ...

        async def cleanup(self) -> None: ...
