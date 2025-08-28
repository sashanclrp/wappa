"""
Database Adapter Protocol

Defines the interface for database adapters that work with SQLModel and
SQLAlchemy async engines. Each adapter handles database-specific connection
patterns, configuration, and schema management.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, AsyncContextManager, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlmodel import SQLModel


class DatabaseAdapter(Protocol):
    """
    Universal database adapter interface for SQLModel/SQLAlchemy async connections.

    All database adapters must implement these methods to provide consistent
    database integration across different engines (PostgreSQL, SQLite, MySQL).
    """

    async def create_engine(
        self, connection_string: str, **kwargs: Any
    ) -> "AsyncEngine":
        """
        Create an async SQLAlchemy engine for the database.

        Args:
            connection_string: Database connection URL
            **kwargs: Engine-specific configuration options

        Returns:
            Configured AsyncEngine instance

        Raises:
            ConnectionError: If unable to create engine
        """
        ...

    async def create_session_factory(
        self, engine: "AsyncEngine"
    ) -> Callable[[], AsyncContextManager["AsyncSession"]]:
        """
        Create a session factory for the database engine.

        The returned factory creates async context managers that yield
        AsyncSession instances for database operations.

        Args:
            engine: AsyncEngine instance

        Returns:
            Callable that returns AsyncSession context manager

        Example:
            session_factory = await adapter.create_session_factory(engine)
            async with session_factory() as session:
                # Use session for database operations
                pass
        """
        ...

    async def initialize_schema(
        self, engine: "AsyncEngine", models: list[type["SQLModel"]] = None
    ) -> None:
        """
        Initialize database schema from SQLModel definitions.

        Creates all tables defined by the provided SQLModel classes.
        Handles database-specific schema creation patterns.

        Args:
            engine: AsyncEngine instance
            models: List of SQLModel classes to create tables for
                   If None, creates all tables from metadata

        Raises:
            DatabaseError: If schema creation fails
        """
        ...

    async def health_check(self, engine: "AsyncEngine") -> bool:
        """
        Perform a health check on the database connection.

        Args:
            engine: AsyncEngine instance to check

        Returns:
            True if database is healthy and responsive
        """
        ...

    async def get_connection_info(self, engine: "AsyncEngine") -> dict[str, Any]:
        """
        Get information about the database connection.

        Args:
            engine: AsyncEngine instance

        Returns:
            Dictionary with connection information (driver, version, etc.)
        """
        ...
