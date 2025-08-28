"""
Database Plugin

Core plugin for integrating SQLModel/SQLAlchemy database functionality
with the Wappa framework. Supports multiple database engines through
adapter pattern.
"""

from typing import TYPE_CHECKING, Any

from ...core.logging.logger import get_app_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlmodel import SQLModel

    from ...core.factory.wappa_builder import WappaBuilder
    from ...database.adapter import DatabaseAdapter


class DatabasePlugin:
    """
    Universal database plugin for SQLModel/SQLAlchemy integration.

    This plugin provides database connectivity, session management, and
    schema initialization for any supported database engine (PostgreSQL,
    SQLite, MySQL) through the adapter pattern.

    Example:
        # PostgreSQL
        db_plugin = DatabasePlugin(
            "postgresql+asyncpg://user:pass@localhost/db",
            PostgreSQLAdapter(),
            models=[User, Order]
        )

        # SQLite
        db_plugin = DatabasePlugin(
            "sqlite+aiosqlite:///./app.db",
            SQLiteAdapter(),
            models=[User, Order]
        )

        # Usage in app
        async with app.state.db_session() as session:
            users = await session.exec(select(User))
    """

    def __init__(
        self,
        connection_string: str,
        adapter: "DatabaseAdapter",
        models: list[type["SQLModel"]] = None,
        initialize_schema: bool = True,
        **adapter_kwargs: Any,
    ):
        """
        Initialize database plugin.

        Args:
            connection_string: Database connection URL
            adapter: DatabaseAdapter implementation (PostgreSQL, SQLite, MySQL)
            models: List of SQLModel classes to create tables for
            initialize_schema: Whether to create tables on startup
            **adapter_kwargs: Additional arguments for database adapter
        """
        self.connection_string = connection_string
        self.adapter = adapter
        self.models = models or []
        self.initialize_schema = initialize_schema
        self.adapter_kwargs = adapter_kwargs

        self.engine = None
        self.session_factory = None

    async def configure(self, builder: "WappaBuilder") -> None:
        """
        Configure the database plugin with WappaBuilder.

        This method is called during build phase - no configuration needed
        for database plugin as it manages its own lifecycle.

        Args:
            builder: WappaBuilder instance
        """
        # Database plugin doesn't need to configure middleware/routes
        pass

    async def startup(self, app: "FastAPI") -> None:
        """
        Initialize database during application startup.

        Creates the async engine, session factory, and optionally
        initializes the database schema from SQLModel definitions.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            # Create async engine
            logger.debug(
                f"Creating database engine with adapter: {self.adapter.__class__.__name__}"
            )
            self.engine = await self.adapter.create_engine(
                self.connection_string, **self.adapter_kwargs
            )

            # Create session factory
            logger.debug("Creating database session factory...")
            self.session_factory = await self.adapter.create_session_factory(
                self.engine
            )

            # Perform health check
            is_healthy = await self.adapter.health_check(self.engine)
            if not is_healthy:
                raise RuntimeError("Database health check failed")

            # Initialize schema if requested and models provided
            if self.initialize_schema and self.models:
                logger.debug(f"Initializing schema for {len(self.models)} models...")
                await self.adapter.initialize_schema(self.engine, self.models)
                logger.info(
                    f"Database schema initialized for models: {[m.__name__ for m in self.models]}"
                )

            # Store in app state for user access
            app.state.db_engine = self.engine
            app.state.db_session = self.session_factory
            app.state.db_adapter = self.adapter

            # Get connection info for logging
            connection_info = await self.adapter.get_connection_info(self.engine)
            logger.info(
                f"Database plugin initialized successfully - "
                f"Driver: {connection_info.get('driver')}, "
                f"Database: {connection_info.get('database')}, "
                f"Version: {connection_info.get('version', 'unknown')}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize database plugin: {e}", exc_info=True)
            raise RuntimeError(f"Database plugin startup failed: {e}") from e

    async def shutdown(self, app: "FastAPI") -> None:
        """
        Clean up database resources during application shutdown.

        Properly disposes of the async engine and cleans up connections.

        Args:
            app: FastAPI application instance
        """
        logger = get_app_logger()

        try:
            if self.engine:
                logger.debug("Disposing database engine...")
                await self.engine.dispose()
                logger.info("Database engine disposed successfully")

            # Clean up app state
            if hasattr(app.state, "db_engine"):
                del app.state.db_engine
            if hasattr(app.state, "db_session"):
                del app.state.db_session
            if hasattr(app.state, "db_adapter"):
                del app.state.db_adapter

        except Exception as e:
            logger.error(f"Error during database plugin shutdown: {e}", exc_info=True)

    async def get_health_status(self, app: "FastAPI") -> dict[str, Any]:
        """
        Get database health status for monitoring.

        Args:
            app: FastAPI application instance

        Returns:
            Dictionary with database health information
        """
        if not self.engine:
            return {
                "healthy": False,
                "error": "Database engine not initialized",
                "adapter": self.adapter.__class__.__name__,
            }

        try:
            is_healthy = await self.adapter.health_check(self.engine)
            connection_info = await self.adapter.get_connection_info(self.engine)

            return {
                "healthy": is_healthy,
                "adapter": self.adapter.__class__.__name__,
                "connection_string": self._mask_connection_string(),
                **connection_info,
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "adapter": self.adapter.__class__.__name__,
            }

    def _mask_connection_string(self) -> str:
        """
        Mask sensitive information in connection string for logging.

        Returns:
            Connection string with password masked
        """
        if "://" not in self.connection_string:
            return self.connection_string

        parts = self.connection_string.split("://", 1)
        if len(parts) != 2:
            return self.connection_string

        scheme, rest = parts
        if "@" not in rest:
            return self.connection_string

        # Mask password in user:pass@host format
        user_part, host_part = rest.split("@", 1)
        if ":" in user_part:
            user, _ = user_part.split(":", 1)
            masked_user_part = f"{user}:***"
        else:
            masked_user_part = user_part

        return f"{scheme}://{masked_user_part}@{host_part}"
