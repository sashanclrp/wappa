"""
Wappa Database Components

Provides database abstraction and adapters for SQLModel/SQLAlchemy async
connections. Supports multiple database engines with a unified interface.

Clean Architecture: Infrastructure layer database adapters.

Usage:
    # Recommended: 30x-inspired session manager
    from wappa.database import PostgresSessionManager

    # Base adapter protocol
    from wappa.database import DatabaseAdapter

    # Specific database adapters (legacy)
    from wappa.database import PostgreSQLAdapter, MySQLAdapter, SQLiteAdapter
"""

from .adapter import DatabaseAdapter
from .adapters.mysql_adapter import MySQLAdapter
from .adapters.postgresql_adapter import PostgreSQLAdapter
from .adapters.sqlite_adapter import SQLiteAdapter
from .session_manager import PostgresSessionManager, TransientDatabaseError

__all__ = [
    # Session Manager (30x-inspired, recommended)
    "PostgresSessionManager",
    "TransientDatabaseError",
    # Base Adapter Protocol
    "DatabaseAdapter",
    # Database Adapters (Clean Architecture: Infrastructure implementations)
    "PostgreSQLAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
]
