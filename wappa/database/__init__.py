"""
Wappa Database Module

This module provides database abstraction and adapters for SQLModel/SQLAlchemy
async connections. It supports multiple database engines with a unified interface.
"""

from .adapter import DatabaseAdapter
from .adapters.mysql_adapter import MySQLAdapter
from .adapters.postgresql_adapter import PostgreSQLAdapter
from .adapters.sqlite_adapter import SQLiteAdapter

__all__ = [
    "DatabaseAdapter",
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "MySQLAdapter",
]
