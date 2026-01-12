"""
PostgreSQL Database Plugin

Simplified PostgreSQL database plugin inspired by 30x-community pattern.
Provides easy database integration with session management, retry logic,
and write/read replica support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wappa.core.logging.logger import get_app_logger
from wappa.database.session_manager import PostgresSessionManager

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlmodel import SQLModel

    from wappa.core.factory.wappa_builder import WappaBuilder


class PostgresDatabasePlugin:
    """
    Async PostgreSQL database plugin optimized for conversational applications.

    **Optimized for Async Operations**: This plugin uses asyncpg and SQLAlchemy's
    async engine, designed for high-concurrency conversational apps like WhatsApp
    where multiple users send messages simultaneously. Async operations prevent
    blocking and ensure responsive message handling.

    Provides:
    - Async-first API with asyncpg driver for PostgreSQL
    - 30x-inspired session management with retry logic
    - Write/read replica support (future-ready)
    - Auto-table creation at startup
    - Clean injection into WappaEventHandler as self.db
    - Connection pooling for concurrent message handling

    Simple Usage:
        PostgresDatabasePlugin(
            url="postgresql+asyncpg://user:pass@localhost/db"
        )

    Advanced Usage:
        PostgresDatabasePlugin(
            url="postgresql+asyncpg://primary:5432/db",
            read_urls=["postgresql+asyncpg://replica1:5432/db"],
            models=[User, Order],
            auto_create_tables=True,
            auto_commit=True,
            pool_size=30,
            statement_cache_size=0,  # For pgBouncer/Supabase
        )

    In Event Handler (Async):
        class MyEventHandler(WappaEventHandler):
            async def process_message(self, webhook):
                # Async context manager - non-blocking
                async with self.db() as session:
                    result = await session.execute(select(User).where(...))
                    user = result.scalars().first()
                    # Auto-commits on context exit

    Important Notes:
        - Use postgresql+asyncpg:// URLs (not postgresql://)
        - Use session.execute() not session.exec() (SQLAlchemy AsyncSession)
        - All database operations must be awaited
        - Set statement_cache_size=0 for pgBouncer transaction mode
    """

    def __init__(
        self,
        url: str,
        *,
        read_urls: list[str] | None = None,
        models: list[type[SQLModel]] | None = None,
        auto_create_tables: bool = True,
        auto_commit: bool = True,
        pool_size: int = 20,
        max_overflow: int = 40,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        echo: bool = False,
        statement_cache_size: int | None = None,
    ):
        """
        Initialize PostgreSQL database plugin.

        Args:
            url: Primary database URL for write operations
                 Supports: postgresql://, postgres://, postgresql+asyncpg://
            read_urls: Optional list of replica URLs for read operations
            models: List of SQLModel classes for auto-table creation
            auto_create_tables: Whether to create tables at startup (default: True)
            auto_commit: Auto-commit on successful context exit (default: True)
            pool_size: Number of connections in pool (default: 20)
            max_overflow: Max connections beyond pool_size (default: 40)
            pool_timeout: Seconds to wait for connection (default: 30)
            pool_recycle: Recycle connections after N seconds (default: 3600)
            pool_pre_ping: Test connections before use (default: True)
            max_retries: Number of retry attempts for transient failures (default: 3)
            base_delay: Base delay for exponential backoff (default: 1.0)
            max_delay: Maximum delay between retries (default: 30.0)
            echo: Log SQL statements (default: False)
            statement_cache_size: Asyncpg prepared statement cache size.
                Set to 0 to disable (required for pgBouncer transaction mode).
                None (default) uses asyncpg's default behavior.
        """
        self.url = url
        self.read_urls = read_urls or []
        self.models = models or []
        self.auto_create_tables = auto_create_tables
        self.auto_commit = auto_commit

        # Store pool configuration for session manager
        self._pool_config = {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": pool_pre_ping,
            "max_retries": max_retries,
            "base_delay": base_delay,
            "max_delay": max_delay,
            "auto_commit": auto_commit,
            "echo": echo,
            "statement_cache_size": statement_cache_size,
        }

        # Runtime state
        self._session_manager: PostgresSessionManager | None = None

    def configure(self, builder: WappaBuilder) -> None:
        """
        Configure PostgreSQL plugin with WappaBuilder using hook-based architecture.

        Registers database initialization and cleanup as hooks with the builder's
        unified lifespan management system. This ensures database starts after
        core Wappa functionality (logging) and shuts down before core cleanup.

        Args:
            builder: WappaBuilder instance to register hooks with
        """
        # Register database lifecycle hooks with appropriate priorities
        # Priority 25: After Redis (20) but before user hooks (50)
        builder.add_startup_hook(self._db_startup, priority=25)
        builder.add_shutdown_hook(self._db_shutdown, priority=25)

        logger = get_app_logger()
        logger.debug(
            "🔧 PostgresDatabasePlugin configured - registered startup/shutdown hooks"
        )

    async def startup(self, app: FastAPI) -> None:
        """
        Plugin startup method required by WappaPlugin protocol.

        Delegates to _db_startup hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._db_startup(app)

    async def shutdown(self, app: FastAPI) -> None:
        """
        Plugin shutdown method required by WappaPlugin protocol.

        Delegates to _db_shutdown hook method for actual implementation.
        This maintains compatibility with both the plugin protocol and
        the hook-based architecture.

        Args:
            app: FastAPI application instance
        """
        await self._db_shutdown(app)

    async def _db_startup(self, app: FastAPI) -> None:
        """
        Database initialization hook - runs after core Wappa and Redis startup.

        This hook is registered with priority 25, ensuring it runs after
        Redis (priority 20) and core Wappa functionality (priority 10).

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Section header
            logger.info("=== POSTGRESQL DATABASE INITIALIZATION ===")

            # Log database URL (masked) and configuration
            masked_url = self._mask_url(self.url)
            logger.debug(
                f"🐘 Database URL: {masked_url} "
                f"(pool_size: {self._pool_config['pool_size']}, "
                f"max_overflow: {self._pool_config['max_overflow']}, "
                f"timeout: {self._pool_config['pool_timeout']}s)"
            )

            # Log read replicas if configured
            if self.read_urls:
                logger.info(f"📖 Read replicas configured: {len(self.read_urls)}")
                for idx, replica_url in enumerate(self.read_urls, 1):
                    logger.debug(f"   • Replica {idx}: {self._mask_url(replica_url)}")

            # Create session manager
            logger.debug("Creating PostgreSQL session manager...")
            self._session_manager = PostgresSessionManager(
                write_url=self.url,
                read_urls=self.read_urls or None,
                **self._pool_config,
            )

            # Initialize connections
            logger.info("🔌 Initializing database connections...")
            await self._session_manager.initialize()
            logger.debug("✅ Database connection pool initialized")

            # Perform health check
            logger.info("🏥 Verifying database connection health...")
            is_healthy = await self._session_manager.health_check()

            if is_healthy:
                logger.debug("✅ Database health check passed")
            else:
                logger.warning("⚠️ Database health check returned unhealthy status")

            # Create tables if requested and models provided
            if self.auto_create_tables and self.models:
                logger.info(
                    f"📊 Auto-creating tables for {len(self.models)} models: "
                    f"{[m.__name__ for m in self.models]}"
                )
                await self._create_tables()
                logger.debug("✅ Database tables created successfully")
            elif self.models:
                logger.info(
                    f"📋 Models registered (auto_create_tables=False): "
                    f"{[m.__name__ for m in self.models]}"
                )
            else:
                logger.debug("No models registered - skipping table creation")

            # Store session manager in app state for access
            app.state.postgres_session_manager = self._session_manager

            # Get health status for final summary
            health = self._session_manager.get_health_status()

            # Success confirmation
            logger.info(
                f"✅ PostgreSQL database startup completed! "
                f"Status: {'healthy' if is_healthy else 'degraded'}, "
                f"Pool: {health.get('pool_size', 'N/A')}/{health.get('max_overflow', 'N/A')}, "
                f"Read replicas: {len(self.read_urls)}, "
                f"Auto-commit: {self.auto_commit}"
            )

            # Section footer
            logger.info("=" * 43)

            # Debug: Full health status details
            logger.debug(f"Database health details: {health}")

        except Exception as e:
            logger.error(
                f"❌ PostgreSQL database startup hook failed: {e}", exc_info=True
            )
            raise RuntimeError(
                f"PostgresDatabasePlugin startup hook failed: {e}"
            ) from e

    async def _db_shutdown(self, app: FastAPI) -> None:
        """
        Database cleanup hook - runs before core Wappa shutdown.

        This hook is registered with priority 25, ensuring it runs before
        core Wappa cleanup (priority 90) to properly close database connections
        while logging is still available.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Clean up database connections if initialized
            if self._session_manager:
                logger.info("=== POSTGRESQL DATABASE SHUTDOWN ===")
                logger.debug("🐘 Cleaning up database connections...")
                await self._session_manager.cleanup()
                logger.info("✅ PostgreSQL database shutdown completed")
                logger.info("=" * 43)

            # Clean up app state
            if hasattr(app.state, "postgres_session_manager"):
                del app.state.postgres_session_manager
                logger.debug("🧹 Session manager removed from app state")

        except Exception as e:
            # Don't re-raise in shutdown - log and continue
            logger.error(
                f"❌ Error during PostgreSQL shutdown hook: {e}", exc_info=True
            )

    async def _create_tables(self) -> None:
        """
        Create database tables from SQLModel definitions.

        Uses SQLModel.metadata.create_all to create all tables
        for the registered models.
        """
        if not self._session_manager or not self._session_manager.write_engine:
            raise RuntimeError("Session manager not initialized")

        from sqlmodel import SQLModel

        logger = get_app_logger()

        # Ensure all models are imported (triggers table registration in metadata)
        for model in self.models:
            logger.debug(f"Registering model: {model.__name__}")

        # Create tables
        async with self._session_manager.write_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    async def get_health_status(self, app: FastAPI) -> dict[str, Any]:
        """
        Get database health status for monitoring.

        Args:
            app: FastAPI application instance

        Returns:
            Dictionary with database health information
        """
        if not self._session_manager:
            return {
                "healthy": False,
                "error": "Session manager not initialized",
                "plugin": "PostgresDatabasePlugin",
            }

        try:
            is_healthy = await self._session_manager.health_check()
            health_status = self._session_manager.get_health_status()

            return {
                "healthy": is_healthy,
                "plugin": "PostgresDatabasePlugin",
                "write_url": self._mask_url(self.url),
                "read_replicas": len(self.read_urls),
                **health_status,
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "plugin": "PostgresDatabasePlugin",
            }

    def _mask_url(self, url: str) -> str:
        """
        Mask sensitive information in database URL for logging.

        Args:
            url: Database connection URL

        Returns:
            URL with password masked
        """
        if "://" not in url:
            return url

        parts = url.split("://", 1)
        if len(parts) != 2:
            return url

        scheme, rest = parts
        if "@" not in rest:
            return url

        # Mask password in user:pass@host format
        user_part, host_part = rest.split("@", 1)
        if ":" in user_part:
            user, _ = user_part.split(":", 1)
            masked_user_part = f"{user}:***"
        else:
            masked_user_part = user_part

        return f"{scheme}://{masked_user_part}@{host_part}"

    @property
    def session_manager(self) -> PostgresSessionManager | None:
        """Get the session manager (for advanced use cases)."""
        return self._session_manager


__all__ = ["PostgresDatabasePlugin"]
