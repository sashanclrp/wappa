"""
Type-specific cache interfaces for Wappa framework.

Provides specialized interfaces for different cache types with appropriate
method signatures. These interfaces are the preferred way to define cache
contracts as they eliminate the N×M adapter problem.

Each interface defines methods specific to its domain:
- IUserCache: User-scoped data (identity implicit via constructor)
- IStateCache: Handler/session state (keyed by handler_name)
- ITableCache: Table/row data (composite key: table_name + pkid)
- IExpiryCache: Expiry triggers (composite key: action + identifier)
"""

from __future__ import annotations

from .ai_state import IAIStateCache
from .expiry import ExpiryKeyConflictError, IExpiryCache
from .state import IStateCache
from .table import ITableCache, TableRowTransition, TableTransitionResult
from .user import IUserCache

__all__ = [
    "ExpiryKeyConflictError",
    "IAIStateCache",
    "IExpiryCache",
    "IStateCache",
    "ITableCache",
    "IUserCache",
    "TableRowTransition",
    "TableTransitionResult",
]
