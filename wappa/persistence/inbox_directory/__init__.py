"""Concrete Inbox Directory storage on ``ITableCache`` under the System Scope."""

from __future__ import annotations

from .row import InboxDirectoryRow
from .table import (
    ACCOUNT_INDEX_TABLE,
    DIRECTORY_TTL_SECONDS,
    MAX_MUTATION_ATTEMPTS,
    PRIMARY_TABLE,
    InboxDirectoryTable,
)

__all__ = [
    "ACCOUNT_INDEX_TABLE",
    "DIRECTORY_TTL_SECONDS",
    "MAX_MUTATION_ATTEMPTS",
    "PRIMARY_TABLE",
    "InboxDirectoryRow",
    "InboxDirectoryTable",
]
