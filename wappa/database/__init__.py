"""
Wappa Database Components

Provides database abstraction and adapters for SQLModel/SQLAlchemy async 
connections. Supports multiple database engines with a unified interface.

Clean Architecture: Infrastructure layer database adapters.

Usage:
    # Base adapter
    from wappa.database import DatabaseAdapter
    
    # Specific database adapters
    from wappa.database import PostgreSQLAdapter, MySQLAdapter, SQLiteAdapter
"""

from .adapter import DatabaseAdapter
from .adapters.mysql_adapter import MySQLAdapter
from .adapters.postgresql_adapter import PostgreSQLAdapter
from .adapters.sqlite_adapter import SQLiteAdapter

__all__ = [
    # Base Adapter
    "DatabaseAdapter",
    
    # Database Adapters (Clean Architecture: Infrastructure implementations)
    "PostgreSQLAdapter",
    "MySQLAdapter", 
    "SQLiteAdapter",
]
