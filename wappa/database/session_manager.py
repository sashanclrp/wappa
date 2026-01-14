"""
PostgreSQL Session Manager

30x-community inspired session management with retry logic, exponential backoff,
and write/read replica support.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("wappa.database.session_manager")


class TransientDatabaseError(Exception):
    """Database error that may be retried (connection timeouts, network issues)."""


class PostgresSessionManager:
    """
    30x-community inspired PostgreSQL session manager with retry logic.

    Features:
    - Connection pooling with configurable parameters (pool_size, max_overflow, pool_timeout)
    - Exponential backoff retry for transient failures
    - Write/read replica support with round-robin selection
    - Connection validation with SELECT 1
    - Health check capabilities
    - Configurable auto-commit behavior

    Example:
        manager = PostgresSessionManager(
            write_url="postgresql://user:pass@localhost/db",
            read_urls=["postgresql://replica1/db", "postgresql://replica2/db"],
        )
        await manager.initialize()

        # Write session
        async with manager.get_session() as session:
            session.add(User(name="test"))
            # Auto-commits on success if auto_commit=True

        # Read session (uses replicas if configured)
        async with manager.get_read_session() as session:
            result = await session.exec(select(User))

        await manager.cleanup()
    """

    # Transient errors that should trigger retry
    _TRANSIENT_ERROR_TYPES = (
        OSError,
        ConnectionError,
        ConnectionRefusedError,
        ConnectionResetError,
        TimeoutError,
    )

    # Error message patterns indicating transient failures
    _TRANSIENT_ERROR_PATTERNS = (
        "connection refused",
        "connection reset",
        "connection timed out",
        "could not connect",
        "server closed the connection",
        "ssl connection has been closed",
        "network is unreachable",
        "no route to host",
        "name resolution failed",
        "name or service not known",
        "dns",
    )

    def __init__(
        self,
        write_url: str,
        read_urls: list[str] | None = None,
        *,
        pool_size: int = 20,
        max_overflow: int = 40,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        auto_commit: bool = True,
        echo: bool = False,
        statement_cache_size: int | None = None,
    ):
        """
        Initialize PostgreSQL session manager.

        Args:
            write_url: Primary database URL for write operations
            read_urls: Optional list of replica URLs for read operations
            pool_size: Number of connections in pool (default: 20)
            max_overflow: Max connections beyond pool_size (default: 40)
            pool_timeout: Seconds to wait for connection (default: 30)
            pool_recycle: Recycle connections after N seconds (default: 3600)
            pool_pre_ping: Test connections before use (default: True)
            max_retries: Number of retry attempts for transient failures (default: 3)
            base_delay: Base delay for exponential backoff (default: 1.0)
            max_delay: Maximum delay between retries (default: 30.0)
            auto_commit: Auto-commit on successful context exit (default: True)
            echo: Log SQL statements (default: False)
            statement_cache_size: Asyncpg prepared statement cache size.
                Set to 0 to disable (required for pgBouncer transaction mode).
                None (default) uses asyncpg's default behavior.
        """
        self.write_url = self._normalize_url(write_url)
        self.read_urls = [self._normalize_url(url) for url in (read_urls or [])]

        # Pool configuration
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping
        self.echo = echo
        self.statement_cache_size = statement_cache_size

        # Retry configuration
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

        # Behavior configuration
        self.auto_commit = auto_commit

        # Runtime state
        self._write_engine: AsyncEngine | None = None
        self._read_engines: list[AsyncEngine] = []
        self._write_session_maker: async_sessionmaker[AsyncSession] | None = None
        self._read_session_makers: list[async_sessionmaker[AsyncSession]] = []
        self._read_index = 0  # For round-robin read replica selection
        self._initialized = False

    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Normalize database URL to use asyncpg driver.

        Args:
            url: Database connection URL

        Returns:
            URL with postgresql+asyncpg:// scheme
        """
        if url.startswith(("postgresql+asyncpg://", "postgres+asyncpg://")):
            return url

        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)

        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)

        raise ValueError(
            f"Invalid PostgreSQL URL: {url}. "
            "Expected postgresql://, postgres://, or postgresql+asyncpg://"
        )

    def _create_engine(self, url: str) -> AsyncEngine:
        """
        Create async engine with configured pool settings.

        Args:
            url: Database connection URL

        Returns:
            Configured AsyncEngine instance
        """
        # Build connect_args from configuration
        connect_args = {}
        if (
            hasattr(self, "statement_cache_size")
            and self.statement_cache_size is not None
        ):
            connect_args["statement_cache_size"] = self.statement_cache_size

        return create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            echo=self.echo,
            connect_args=connect_args if connect_args else None,
        )

    def _create_session_maker(
        self, engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """
        Create session factory for the given engine.

        Args:
            engine: AsyncEngine instance

        Returns:
            async_sessionmaker configured for the engine
        """
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def initialize(self) -> None:
        """
        Initialize database engines and session factories.

        Creates write engine and optionally read engines for replicas.
        Performs initial health check with retry logic to handle transient failures
        during container startup, DNS resolution, and network glitches.

        Raises:
            ConnectionError: If unable to connect to primary database after retries
        """
        if self._initialized:
            logger.warning("PostgresSessionManager already initialized")
            return

        logger.info("Initializing PostgresSessionManager...")

        # Create write engine
        self._write_engine = self._create_engine(self.write_url)
        self._write_session_maker = self._create_session_maker(self._write_engine)

        # Create read engines (if replicas configured)
        for read_url in self.read_urls:
            read_engine = self._create_engine(read_url)
            self._read_engines.append(read_engine)
            self._read_session_makers.append(self._create_session_maker(read_engine))

        # Validate primary connection with retry logic (critical - must succeed)
        if not await self._initialize_with_retry(
            engine=self._write_engine, is_primary=True
        ):
            await self.cleanup()
            raise ConnectionError(
                f"Failed to connect to primary database after {self.max_retries} attempts"
            )

        # Validate read replicas with retry logic (non-critical - warn on failure)
        # Build lists of healthy replicas only
        healthy_engines: list[AsyncEngine] = []
        healthy_session_makers: list[async_sessionmaker[AsyncSession]] = []

        for idx, (read_engine, session_maker) in enumerate(
            zip(self._read_engines, self._read_session_makers, strict=True)
        ):
            if await self._initialize_with_retry(
                engine=read_engine, is_primary=False, replica_index=idx
            ):
                healthy_engines.append(read_engine)
                healthy_session_makers.append(session_maker)
            else:
                # Dispose failed replica engine to free resources
                try:
                    await read_engine.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing failed replica {idx + 1}: {e}")
                logger.warning(
                    f"Read replica {idx + 1} failed health check after retries - "
                    f"removed from read pool"
                )

        # Replace with healthy replicas only
        total_replicas = len(self._read_engines)
        self._read_engines = healthy_engines
        self._read_session_makers = healthy_session_makers

        self._initialized = True

        logger.info(
            f"PostgresSessionManager initialized successfully "
            f"(pool_size={self.pool_size}, max_overflow={self.max_overflow}, "
            f"read_replicas={len(healthy_engines)}/{total_replicas})"
        )

    async def cleanup(self) -> None:
        """
        Dispose all database engines and cleanup resources.

        Ensures proper connection cleanup to prevent session leaks.
        """
        logger.info("Cleaning up PostgresSessionManager...")

        # Dispose read engines
        for engine in self._read_engines:
            try:
                await engine.dispose()
            except Exception as e:
                logger.warning(f"Error disposing read engine: {e}")

        self._read_engines.clear()
        self._read_session_makers.clear()

        # Dispose write engine
        if self._write_engine:
            try:
                await self._write_engine.dispose()
                logger.info("Write engine disposed successfully")
            except Exception as e:
                logger.warning(f"Error disposing write engine: {e}")
            self._write_engine = None
            self._write_session_maker = None

        self._initialized = False
        logger.info("PostgresSessionManager cleanup complete")

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient and should be retried.

        Args:
            error: Exception to check

        Returns:
            True if error is likely transient and retryable
        """
        # Check error type
        if isinstance(error, self._TRANSIENT_ERROR_TYPES):
            return True

        # Check error message patterns
        error_msg = str(error).lower()
        return any(pattern in error_msg for pattern in self._TRANSIENT_ERROR_PATTERNS)

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
        return min(delay, self.max_delay)

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
        db_type = (
            "primary database" if is_primary else f"read replica {replica_index + 1}"
        )
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # Perform health check on specific engine
                async with engine.begin() as conn:
                    result = await conn.execute(text("SELECT 1"))
                    if result.scalar() == 1:
                        if attempt > 0:
                            logger.info(
                                f"{db_type.capitalize()} connection established "
                                f"on attempt {attempt + 1}/{self.max_retries}"
                            )
                        return True

                # Health check returned unexpected result
                error_msg = (
                    f"{db_type.capitalize()} health check returned unexpected result"
                )
                logger.warning(
                    f"{error_msg} (attempt {attempt + 1}/{self.max_retries})"
                )

                # Treat unexpected result as transient
                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"Retrying {db_type} in {delay:.2f}s...")
                    await asyncio.sleep(delay)

            except Exception as e:
                last_exception = e

                # Check if error is transient
                if not self._is_transient_error(e):
                    logger.error(f"Non-transient error connecting to {db_type}: {e}")
                    return False

                # Log and retry for transient errors
                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        f"{db_type.capitalize()} connection failed "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        if last_exception:
            logger.error(
                f"{db_type.capitalize()} connection failed after "
                f"{self.max_retries} attempts: {last_exception}"
            )

        return False

    @asynccontextmanager
    async def _session_with_retry(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        operation_name: str = "Database",
    ) -> AsyncIterator[AsyncSession]:
        """
        Shared retry logic for session management.

        Uses exponential backoff for transient failures.
        Validates connection before yielding session.
        Auto-commits on success if auto_commit=True.

        Args:
            session_maker: Session factory to use
            operation_name: Name for logging (e.g., "Database", "Read database")

        Yields:
            AsyncSession for database operations

        Raises:
            TransientDatabaseError: After max retries exceeded
            Exception: For non-transient database errors
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                async with session_maker() as session:
                    # Connection validation (30x pattern)
                    try:
                        await session.execute(text("SELECT 1"))
                    except Exception as e:
                        logger.warning(f"Connection validation failed: {e}")
                        raise

                    try:
                        yield session
                        if self.auto_commit:
                            await session.commit()
                    except Exception:
                        await session.rollback()
                        raise
                    return

            except Exception as e:
                last_exception = e

                if not self._is_transient_error(e):
                    # Non-transient error - don't retry
                    raise

                if attempt < self.max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        f"{operation_name} operation failed (attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"{operation_name} operation failed after {self.max_retries} attempts: {e}"
                    )

        raise TransientDatabaseError(
            f"{operation_name} operation failed after {self.max_retries} attempts"
        ) from last_exception

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get write session with retry logic.

        Uses exponential backoff for transient failures.
        Validates connection before yielding session.
        Auto-commits on success if auto_commit=True.

        Yields:
            AsyncSession for write operations

        Raises:
            TransientDatabaseError: After max retries exceeded
            Exception: For non-transient database errors
        """
        if not self._initialized or not self._write_session_maker:
            raise RuntimeError("PostgresSessionManager not initialized")

        async with self._session_with_retry(
            self._write_session_maker, "Database"
        ) as session:
            yield session

    @asynccontextmanager
    async def get_read_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get read session from replica pool (or write if no replicas).

        Uses round-robin selection when multiple replicas are configured.
        Falls back to write database if no replicas available.

        Yields:
            AsyncSession for read operations
        """
        if not self._initialized:
            raise RuntimeError("PostgresSessionManager not initialized")

        # Fallback to write session if no read replicas
        if not self._read_session_makers:
            async with self.get_session() as session:
                yield session
            return

        # Round-robin replica selection
        session_maker = self._read_session_makers[
            self._read_index % len(self._read_session_makers)
        ]
        self._read_index += 1

        async with self._session_with_retry(session_maker, "Read database") as session:
            yield session

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
            logger.error(f"Database health check failed: {e}")
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

        pool = self._write_engine.pool

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


__all__ = ["PostgresSessionManager", "TransientDatabaseError"]
