"""
SQLite Database Adapter

Provides SQLite-specific implementation for SQLModel/SQLAlchemy async connections
using aiosqlite as the async driver.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


class SQLiteAdapter:
    """
    SQLite adapter for SQLModel/SQLAlchemy async connections.

    Uses aiosqlite driver for async SQLite operations.
    Provides connection management, health checks, and schema management
    with SQLite-specific optimizations.
    """

    async def create_engine(self, connection_string: str, **kwargs: Any) -> AsyncEngine:
        """
        Create SQLite async engine with aiosqlite driver.

        Args:
            connection_string: SQLite connection URL (sqlite+aiosqlite://...)
            **kwargs: Engine configuration options

        Returns:
            Configured AsyncEngine for SQLite

        Raises:
            ValueError: If connection string is invalid
            ConnectionError: If unable to create engine
        """
        # Ensure aiosqlite driver is specified
        if not connection_string.startswith("sqlite+aiosqlite://"):
            # Convert standard sqlite:// to aiosqlite version
            if connection_string.startswith("sqlite://"):
                connection_string = connection_string.replace(
                    "sqlite://", "sqlite+aiosqlite://", 1
                )
            else:
                raise ValueError(
                    "SQLite connection string must use sqlite+aiosqlite:// scheme"
                )

        # Default SQLite engine configuration
        default_config = {
            "echo": False,
            "connect_args": {
                "check_same_thread": False,  # Required for async
                "timeout": 30,
            },
            # SQLite doesn't use connection pooling in the traditional sense
            "poolclass": None,
        }
        default_config.update(kwargs)

        try:
            engine = create_async_engine(connection_string, **default_config)
            return engine
        except Exception as e:
            raise ConnectionError(f"Failed to create SQLite engine: {e}") from e

    async def create_session_factory(
        self, engine: AsyncEngine
    ) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        """
        Create session factory for SQLite async sessions.

        Args:
            engine: SQLite AsyncEngine instance

        Returns:
            Session factory function that returns context manager
        """
        # Create async session maker
        async_session_maker = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        @asynccontextmanager
        async def session_factory():
            async with async_session_maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        return session_factory

    async def initialize_schema(
        self, engine: AsyncEngine, models: list[type[SQLModel]] = None
    ) -> None:
        """
        Initialize SQLite schema from SQLModel definitions.

        Args:
            engine: SQLite AsyncEngine instance
            models: List of SQLModel classes to create tables for

        Raises:
            DatabaseError: If schema creation fails
        """
        try:
            async with engine.begin() as conn:
                # Enable foreign key support for SQLite
                await conn.execute("PRAGMA foreign_keys=ON")
                # Create all tables from SQLModel metadata
                await conn.run_sync(SQLModel.metadata.create_all)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize SQLite schema: {e}") from e

    async def health_check(self, engine: AsyncEngine) -> bool:
        """
        Perform SQLite health check.

        Args:
            engine: SQLite AsyncEngine instance

        Returns:
            True if database is healthy and responsive
        """
        try:
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception:
            return False

    async def get_connection_info(self, engine: AsyncEngine) -> dict[str, Any]:
        """
        Get SQLite connection information.

        Args:
            engine: SQLite AsyncEngine instance

        Returns:
            Dictionary with SQLite connection details
        """
        try:
            async with engine.begin() as conn:
                version_result = await conn.execute(text("SELECT sqlite_version()"))
                version = version_result.scalar()

                # Get database file info
                pragma_result = await conn.execute(text("PRAGMA database_list"))
                database_info = pragma_result.fetchall()

                return {
                    "driver": "aiosqlite",
                    "database": "sqlite",
                    "version": version,
                    "database_file": database_info[0][2] if database_info else "memory",
                    "foreign_keys_enabled": True,  # We enable this by default
                    "healthy": True,
                }
        except Exception as e:
            return {
                "driver": "aiosqlite",
                "database": "sqlite",
                "error": str(e),
                "healthy": False,
            }
