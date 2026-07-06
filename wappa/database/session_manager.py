"""
PostgreSQL Session Manager

30x-community inspired session management with retry logic, exponential backoff,
and write/read replica support.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

import anyio
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
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
    - Connection validation at checkout via pool_pre_ping (no eager SELECT 1)
    - Bounded retry of transient connection *establishment* (DNS blips, refused
      connections) before the caller runs any query — see ``_acquire_session``
    - Fast-fail connect timeout so a stalled/unroutable host cannot hang a
      request on asyncpg's ~60s default connect deadline
    - Cancellation-safe session teardown (shielded rollback/close)
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
        command_timeout: float | None = 30.0,
        connect_timeout: float | None = 10.0,
        connect_max_retries: int = 2,
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
            command_timeout: Per-statement timeout in seconds passed to asyncpg
                (default: 30.0). Bounds how long a single query can pin its
                connection, so a stalled query (e.g. blocked on a slow upstream
                lock) cannot hold a server-side transaction open indefinitely.
                Set to None to disable the client-side statement deadline.
            connect_timeout: Per-attempt connect timeout in seconds passed to
                asyncpg (default: 10.0). Without it, a fresh connection to an
                unroutable/stalled host hangs on asyncpg's ~60s default before
                failing, turning a transient network blip into a ~60s zombie
                request. Set to None to fall back to the driver default.
            connect_max_retries: Number of *additional* attempts to establish a
                new connection when checkout raises a transient error — DNS
                blips, connection refused/reset, network unreachable (default:
                2, i.e. 3 attempts total). This retries connection
                *establishment only*, before the caller runs any query, so it is
                safe to replay; the query/transaction path itself never retries.
                Set to 0 to restore fully-lazy acquisition (no eager checkout,
                minimal transaction window) and disable connect retries.
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
        self.command_timeout = command_timeout
        self.connect_timeout = connect_timeout
        self.connect_max_retries = connect_max_retries

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
        # Build connect_args from configuration.
        # NOTE: always pass a dict (never None). create_async_engine chokes on
        # connect_args=None (TypeError: 'NoneType' object is not iterable), so an
        # empty dict must stay an empty dict.
        connect_args: dict = {}
        if self.statement_cache_size is not None:
            connect_args["statement_cache_size"] = self.statement_cache_size
        if self.command_timeout is not None:
            connect_args["command_timeout"] = self.command_timeout
        if self.connect_timeout is not None:
            connect_args["timeout"] = self.connect_timeout

        return create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            echo=self.echo,
            connect_args=connect_args,
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
                    logger.warning("Error disposing failed replica %d: %s", idx + 1, e)
                logger.warning(
                    "Read replica %d failed health check after retries — removed from read pool",
                    idx + 1,
                )

        # Replace with healthy replicas only
        total_replicas = len(self._read_engines)
        self._read_engines = healthy_engines
        self._read_session_makers = healthy_session_makers

        self._initialized = True

        logger.info(
            "PostgresSessionManager initialized successfully "
            "(pool_size=%d, max_overflow=%d, read_replicas=%d/%d)",
            self.pool_size,
            self.max_overflow,
            len(healthy_engines),
            total_replicas,
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
                await engine.dispose(close=False)
            except Exception as e:
                logger.warning("Error disposing read engine: %s", e)

        self._read_engines.clear()
        self._read_session_makers.clear()

        # Dispose write engine
        if self._write_engine:
            try:
                await self._write_engine.dispose(close=False)
                logger.info("Write engine disposed successfully")
            except Exception as e:
                logger.warning("Error disposing write engine: %s", e)
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
        # Pool exhaustion (QueuePool checkout timeout) is NOT transient: the pool
        # is drained, so retrying just parks the request and saturates the pooler
        # further. SQLAlchemy raises exc.TimeoutError with a message containing
        # "connection timed out", which would otherwise match the patterns below —
        # classify it as non-transient explicitly and fail fast.
        if isinstance(error, SQLAlchemyTimeoutError):
            return False

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

    @staticmethod
    async def _shielded(coro: Awaitable[None], *, timeout: float = 10.0) -> None:
        """
        Run a teardown coroutine shielded from outer cancellation.

        Session teardown (rollback/close) must reach Postgres even when the
        request is being cancelled — otherwise the server-side backend is left
        orphaned mid-transaction (``idle in transaction``) and the pool leaks.

        ``asyncio.CancelledError`` derives from ``BaseException`` (not
        ``Exception``), and every ``BaseHTTPMiddleware`` layer wraps the request
        in an anyio cancel scope, so a plain ``await session.rollback()`` gets
        cancelled before the ROLLBACK/DISCARD is sent. ``move_on_after(shield=True)``
        protects the teardown; the timeout bounds it so a dead connection cannot
        wedge cleanup forever (pairs with ``command_timeout``).

        Args:
            coro: Teardown coroutine to run (e.g. ``session.rollback()``).
            timeout: Maximum seconds to spend on teardown before giving up.
        """
        try:
            with anyio.move_on_after(timeout, shield=True):
                await coro
        except Exception as e:  # noqa: BLE001 - teardown must never mask the real error
            logger.warning("Session teardown failed (ignored): %s", e)

    async def _acquire_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        operation_name: str,
    ) -> AsyncSession:
        """
        Create a session and eagerly establish its connection, retrying only
        transient *connection-establishment* failures.

        The failure this closes is a **brand-new** connection failing to open —
        a DNS blip, connection refused/reset, or unroutable host while the pool
        is growing. ``pool_pre_ping`` already recycles a *stale* pooled
        connection transparently; what it cannot do is retry a fresh connect
        that never succeeds, and that error would otherwise escape into the
        caller's first query where retry is unsafe.

        Retrying here is safe precisely because it happens **before the caller
        runs anything**: no user query has executed, so tearing down a
        half-open session and creating a fresh one is indistinguishable from the
        first attempt. Once the connection is live we return the session and
        never retry again — an in-flight transaction cannot be replayed (that is
        why ``_managed_session`` / ``get_session`` remain non-retrying).

        Forcing the checkout with ``session.connection()`` adds no extra
        round-trip: ``pool_pre_ping`` validates the connection either way; we
        only move the checkout earlier so a connect failure is catchable and
        retryable instead of surfacing mid-handler. Transient classification and
        backoff reuse ``_is_transient_error`` / ``_calculate_backoff``.

        When ``connect_max_retries == 0`` this collapses to fully-lazy
        acquisition (no eager checkout), preserving the minimal transaction
        window and disabling connect retries.

        Args:
            session_maker: Session factory to use.
            operation_name: Name for logging (e.g. "Database", "Read database").

        Returns:
            An ``AsyncSession`` whose connection is already established (or a
            fresh, not-yet-connected session when ``connect_max_retries == 0``).

        Raises:
            Exception: The last transient error after retries are exhausted, or
                immediately for any non-transient / non-``Exception`` failure
                (e.g. ``CancelledError``).
        """
        if self.connect_max_retries <= 0:
            return session_maker()

        attempt = 0
        while True:
            session = session_maker()
            try:
                # Force pool checkout + pre_ping now so a failing connect raises
                # here (retryable) rather than inside the caller's first query.
                await session.connection()
                return session
            except BaseException as exc:
                # Always release the half-open session before retrying/raising.
                await self._shielded(session.close())

                # Never retry cancellation (BaseException, not Exception),
                # non-transient errors (bad creds, SQL), or once exhausted.
                if (
                    not isinstance(exc, Exception)
                    or not self._is_transient_error(exc)
                    or attempt >= self.connect_max_retries
                ):
                    raise

                delay = self._calculate_backoff(attempt)
                logger.warning(
                    "%s connection acquisition failed (attempt %d/%d): %s. "
                    "Retrying in %.2fs...",
                    operation_name,
                    attempt + 1,
                    self.connect_max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

    @asynccontextmanager
    async def _managed_session(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        operation_name: str = "Database",
    ) -> AsyncIterator[AsyncSession]:
        """
        Yield a session with cancellation-safe commit/rollback/close.

        Connection *establishment* is retried once per transient failure via
        ``_acquire_session`` (bounded by ``connect_max_retries``), before the
        caller runs any query. Beyond that this path is intentionally
        **non-retrying**: the session's transaction begins on the first real
        query, so once the handler is using the session it cannot be safely
        replayed. Dead-connection-at-checkout is covered by ``pool_pre_ping``;
        startup connectivity by ``_initialize_with_retry``. There is no eager
        ``SELECT 1``, so the transaction window still tracks actual query time
        rather than spanning the whole request.

        Teardown runs under ``_shielded`` so cancellation (anyio cancel scope /
        ``asyncio.CancelledError``, both ``BaseException``) cannot prevent the
        ROLLBACK/DISCARD from reaching Postgres.

        Args:
            session_maker: Session factory to use
            operation_name: Name for logging (e.g., "Database", "Read database")

        Yields:
            AsyncSession for database operations
        """
        session = await self._acquire_session(session_maker, operation_name)
        try:
            yield session
            if self.auto_commit:
                await self._shielded(session.commit())
        except BaseException:
            # Catch BaseException (not Exception) so cancellation still rolls back.
            await self._shielded(session.rollback())
            raise
        finally:
            await self._shielded(session.close())

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """
        Get write session with cancellation-safe teardown.

        Auto-commits on success if auto_commit=True. Commit/rollback/close run
        shielded from cancellation so the transaction is always resolved on the
        server (see ``_managed_session``). This path does not retry.

        Yields:
            AsyncSession for write operations

        Raises:
            Exception: Propagated unchanged from database operations.
        """
        if not self._initialized or not self._write_session_maker:
            raise RuntimeError("PostgresSessionManager not initialized")

        async with self._managed_session(
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

        async with self._managed_session(session_maker, "Read database") as session:
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
