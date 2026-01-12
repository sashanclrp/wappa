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
    Simplified PostgreSQL database plugin inspired by 30x-community pattern.

    Provides:
    - Simple API: Just pass the connection URL
    - 30x-inspired session management with retry logic
    - Write/read replica support (future-ready)
    - Auto-table creation at startup
    - Clean injection into WappaEventHandler as self.db

    Simple Usage:
        PostgresDatabasePlugin(url="postgresql://user:pass@localhost/db")

    Advanced Usage:
        PostgresDatabasePlugin(
            url="postgresql://primary:5432/db",
            read_urls=["postgresql://replica1:5432/db"],
            models=[User, Order],
            auto_create_tables=True,
            auto_commit=True,
            pool_size=30,
        )

    In Event Handler:
        class MyEventHandler(WappaEventHandler):
            async def process_message(self, webhook):
                async with self.db() as session:
                    user = await session.exec(select(User).where(...))
                    # Auto-commits on context exit
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
        }

        # Runtime state
        self._session_manager: PostgresSessionManager | None = None

    def configure(self, builder: WappaBuilder) -> None:
        """
        Configure the plugin with WappaBuilder.

        Database plugin doesn't need sync configuration - all setup
        happens during async startup.

        Args:
            builder: WappaBuilder instance
        """
        # No sync configuration needed for database plugin
        pass

    async def startup(self, app: FastAPI) -> None:
        """
        Initialize database during application startup.

        Creates the PostgresSessionManager, initializes connections,
        and optionally creates tables from SQLModel definitions.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            logger.info("Starting PostgresDatabasePlugin...")

            # Create session manager
            self._session_manager = PostgresSessionManager(
                write_url=self.url,
                read_urls=self.read_urls or None,
                **self._pool_config,
            )

            # Initialize connections
            await self._session_manager.initialize()

            # Create tables if requested and models provided
            if self.auto_create_tables and self.models:
                await self._create_tables()
                logger.info(
                    f"Database tables created for models: {[m.__name__ for m in self.models]}"
                )

            # Store session manager in app state for access
            app.state.postgres_session_manager = self._session_manager

            # Log success
            health = self._session_manager.get_health_status()
            logger.info(
                f"PostgresDatabasePlugin initialized successfully - "
                f"pool_size={health.get('pool_size', 'N/A')}, "
                f"read_replicas={len(self.read_urls)}, "
                f"auto_commit={self.auto_commit}"
            )

        except Exception as e:
            logger.error(
                f"Failed to initialize PostgresDatabasePlugin: {e}", exc_info=True
            )
            raise RuntimeError(f"PostgresDatabasePlugin startup failed: {e}") from e

    async def shutdown(self, app: FastAPI) -> None:
        """
        Clean up database resources during application shutdown.

        Properly disposes of all engines and connections.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            if self._session_manager:
                logger.info("Shutting down PostgresDatabasePlugin...")
                await self._session_manager.cleanup()
                logger.info("PostgresDatabasePlugin shutdown complete")

            # Clean up app state
            if hasattr(app.state, "postgres_session_manager"):
                del app.state.postgres_session_manager

        except Exception as e:
            logger.error(
                f"Error during PostgresDatabasePlugin shutdown: {e}", exc_info=True
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
