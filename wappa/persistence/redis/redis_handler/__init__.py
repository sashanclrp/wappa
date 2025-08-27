"""
Redis Handler Module for Wappa Cache

Repository classes for Redis cache operations with clean separation of concerns.
Each class handles a specific cache domain: users, state handlers, and tables.
"""

# Core cache handlers
from .state_handler import RedisStateHandler
from .table import RedisTable
from .user import RedisUser

# Utils
from .utils import KeyFactory, TenantCache, dumps, loads

__all__ = [
    # Infrastructure
    "KeyFactory",
    "dumps",
    "loads",
    "TenantCache",
    # Cache Repositories
    "RedisUser",
    "RedisStateHandler",
    "RedisTable",
]
