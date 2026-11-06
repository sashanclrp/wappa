"""PostgreSQL Session Manager

30x-community inspired session management with retry logic, exponential backoff,
and write/read replica support.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from wappa.database.session_manager import _engine
from wappa.database.session_manager._health import _HealthMixin
from wappa.database.session_manager._retry import _RetryMixin
from wappa.database.session_manager._sessions import _SessionMixin

logger = logging.getLogger("wappa.database.session_manager")


class PostgresSessionManager(_SessionMixin, _HealthMixin, _RetryMixin):
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
        return _engine.normalize_url(url)

    def _create_engine(self, url: str) -> AsyncEngine:
        """
        Create async engine with configured pool settings.

        Args:
            url: Database connection URL

        Returns:
            Configured AsyncEngine instance
        """
        return _engine.create_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_timeout=self.pool_timeout,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            echo=self.echo,
            statement_cache_size=self.statement_cache_size,
            command_timeout=self.command_timeout,
            connect_timeout=self.connect_timeout,
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
        return _engine.create_session_maker(engine)

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
