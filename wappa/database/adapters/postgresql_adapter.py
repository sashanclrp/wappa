"""
PostgreSQL Database Adapter

Provides PostgreSQL-specific implementation for SQLModel/SQLAlchemy async connections
using asyncpg as the async driver.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


class PostgreSQLAdapter:
    """
    PostgreSQL adapter for SQLModel/SQLAlchemy async connections.

    Uses asyncpg driver for optimal PostgreSQL async performance.
    Provides connection pooling, health checks, and schema management.
    """

    async def create_engine(self, connection_string: str, **kwargs: Any) -> AsyncEngine:
        """
        Create PostgreSQL async engine with asyncpg driver.

        Args:
            connection_string: PostgreSQL connection URL (postgresql+asyncpg://...)
            **kwargs: Engine configuration options

        Returns:
            Configured AsyncEngine for PostgreSQL

        Raises:
            ValueError: If connection string is invalid
            ConnectionError: If unable to create engine
        """
        # Ensure asyncpg driver is specified
        if not connection_string.startswith(
            ("postgresql+asyncpg://", "postgres+asyncpg://")
        ):
            # Convert standard postgresql:// to asyncpg version
            if connection_string.startswith(("postgresql://", "postgres://")):
                connection_string = connection_string.replace(
                    "postgresql://", "postgresql+asyncpg://", 1
                ).replace("postgres://", "postgresql+asyncpg://", 1)
            else:
                raise ValueError(
                    "PostgreSQL connection string must use postgresql+asyncpg:// scheme"
                )

        # Default PostgreSQL engine configuration
        default_config = {
            "pool_size": 20,
            "max_overflow": 40,
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "echo": False,
        }
        default_config.update(kwargs)

        try:
            engine = create_async_engine(connection_string, **default_config)
            return engine
        except Exception as e:
            raise ConnectionError(f"Failed to create PostgreSQL engine: {e}") from e

    async def create_session_factory(
        self, engine: AsyncEngine
    ) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        """
        Create session factory for PostgreSQL async sessions.

        Args:
            engine: PostgreSQL AsyncEngine instance

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
        Initialize PostgreSQL schema from SQLModel definitions.

        Args:
            engine: PostgreSQL AsyncEngine instance
            models: List of SQLModel classes to create tables for

        Raises:
            DatabaseError: If schema creation fails
        """
        try:
            async with engine.begin() as conn:
                # Create all tables from SQLModel metadata
                await conn.run_sync(SQLModel.metadata.create_all)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize PostgreSQL schema: {e}") from e

    async def health_check(self, engine: AsyncEngine) -> bool:
        """
        Perform PostgreSQL health check.

        Args:
            engine: PostgreSQL AsyncEngine instance

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
        Get PostgreSQL connection information.

        Args:
            engine: PostgreSQL AsyncEngine instance

        Returns:
            Dictionary with PostgreSQL connection details
        """
        try:
            async with engine.begin() as conn:
                version_result = await conn.execute(text("SELECT version()"))
                version = version_result.scalar()

                return {
                    "driver": "asyncpg",
                    "database": "postgresql",
                    "version": version,
                    "pool_size": engine.pool.size(),
                    "pool_checked_in": engine.pool.checkedin(),
                    "pool_checked_out": engine.pool.checkedout(),
                }
        except Exception as e:
            return {
                "driver": "asyncpg",
                "database": "postgresql",
                "error": str(e),
                "healthy": False,
            }
