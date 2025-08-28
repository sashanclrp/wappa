"""
Database Adapters Module

Contains specific database adapter implementations for SQLModel/SQLAlchemy
async engines. Each adapter handles database-specific connection patterns,
configuration, and optimization.
"""

from .mysql_adapter import MySQLAdapter
from .postgresql_adapter import PostgreSQLAdapter
from .sqlite_adapter import SQLiteAdapter

__all__ = [
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "MySQLAdapter",
]
