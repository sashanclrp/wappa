"""
MySQL Database Adapter

Provides MySQL-specific implementation for SQLModel/SQLAlchemy async connections
using aiomysql as the async driver.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel


class MySQLAdapter:
    """
    MySQL adapter for SQLModel/SQLAlchemy async connections.

    Uses aiomysql driver for async MySQL operations.
    Provides connection pooling, health checks, and schema management
    with MySQL-specific optimizations.
    """

    async def create_engine(self, connection_string: str, **kwargs: Any) -> AsyncEngine:
        """
        Create MySQL async engine with aiomysql driver.

        Args:
            connection_string: MySQL connection URL (mysql+aiomysql://...)
            **kwargs: Engine configuration options

        Returns:
            Configured AsyncEngine for MySQL

        Raises:
            ValueError: If connection string is invalid
            ConnectionError: If unable to create engine
        """
        # Ensure aiomysql driver is specified
        if not connection_string.startswith("mysql+aiomysql://"):
            # Convert standard mysql:// to aiomysql version
            if connection_string.startswith("mysql://"):
                connection_string = connection_string.replace(
                    "mysql://", "mysql+aiomysql://", 1
                )
            else:
                raise ValueError(
                    "MySQL connection string must use mysql+aiomysql:// scheme"
                )

        # Default MySQL engine configuration
        default_config = {
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 30,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "echo": False,
            "connect_args": {
                "charset": "utf8mb4",
                "autocommit": False,
            },
        }
        default_config.update(kwargs)

        try:
            engine = create_async_engine(connection_string, **default_config)
            return engine
        except Exception as e:
            raise ConnectionError(f"Failed to create MySQL engine: {e}") from e

    async def create_session_factory(
        self, engine: AsyncEngine
    ) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        """
        Create session factory for MySQL async sessions.

        Args:
            engine: MySQL AsyncEngine instance

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
        Initialize MySQL schema from SQLModel definitions.

        Args:
            engine: MySQL AsyncEngine instance
            models: List of SQLModel classes to create tables for

        Raises:
            DatabaseError: If schema creation fails
        """
        try:
            async with engine.begin() as conn:
                # Set MySQL specific settings for better compatibility
                await conn.execute(
                    "SET sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'"
                )
                # Create all tables from SQLModel metadata
                await conn.run_sync(SQLModel.metadata.create_all)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize MySQL schema: {e}") from e

    async def health_check(self, engine: AsyncEngine) -> bool:
        """
        Perform MySQL health check.

        Args:
            engine: MySQL AsyncEngine instance

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
        Get MySQL connection information.

        Args:
            engine: MySQL AsyncEngine instance

        Returns:
            Dictionary with MySQL connection details
        """
        try:
            async with engine.begin() as conn:
                version_result = await conn.execute(text("SELECT VERSION()"))
                version = version_result.scalar()

                # Get character set info
                charset_result = await conn.execute(
                    text("SELECT @@character_set_database")
                )
                charset = charset_result.scalar()

                # Get collation info
                collation_result = await conn.execute(
                    text("SELECT @@collation_database")
                )
                collation = collation_result.scalar()

                return {
                    "driver": "aiomysql",
                    "database": "mysql",
                    "version": version,
                    "charset": charset,
                    "collation": collation,
                    "pool_size": engine.pool.size(),
                    "pool_checked_in": engine.pool.checkedin(),
                    "pool_checked_out": engine.pool.checkedout(),
                    "healthy": True,
                }
        except Exception as e:
            return {
                "driver": "aiomysql",
                "database": "mysql",
                "error": str(e),
                "healthy": False,
            }
