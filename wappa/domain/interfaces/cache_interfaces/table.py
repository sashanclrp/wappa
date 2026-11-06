"""Table/row cache interface (composite key: table_name + pkid) and atomic transition types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class TableRowTransition(StrEnum):
    """The one thing an atomic row transition proves about a table row.

    ``CREATED`` and ``REPLACED`` are the only outcomes that wrote. The other
    three are refusals, and each names a different reason so a caller can tell
    "someone else got there first" apart from "the row moved on without me"
    apart from "there is nothing here to move".
    """

    CREATED = "created"
    REPLACED = "replaced"
    ALREADY_EXISTS = "already_exists"
    CONDITION_NOT_MET = "condition_not_met"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class TableTransitionResult:
    """Outcome of one atomic row transition, plus the row that blocked it.

    ``row`` carries the state the backend actually holds when the transition
    was refused — the winning row for ``ALREADY_EXISTS``, the current row for
    ``CONDITION_NOT_MET``. That saves the caller a follow-up read whose answer
    could already be stale. It is ``None`` after a successful write (the caller
    supplied that data) and after ``MISSING`` (there is nothing to report).
    """

    transition: TableRowTransition
    row: dict[str, Any] | None = None

    @property
    def written(self) -> bool:
        """Whether this call is the one that wrote the row."""
        return self.transition in (
            TableRowTransition.CREATED,
            TableRowTransition.REPLACED,
        )


class ITableCache(ABC):
    """
    Interface for table/row cache operations.

    Data is keyed by composite key (table_name + pkid).

    The namespace is a Table Cache Scope, not necessarily an Inbox: the
    reserved System Scope, a Host-defined business scope, or an Inbox
    namespace. It is established by the ``context_id`` constructor parameter.

    Example:
        table = RedisTable(context_id="myapp")
        await table.upsert("products", "sku123", {"name": "Widget", "price": 99})
        data = await table.get("products", "sku123")
    """

    @abstractmethod
    async def get(
        self,
        table_name: str,
        pkid: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            models: Optional BaseModel class for deserialization

        Returns:
            Table row data or None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """
        Create or update table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            data: Data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def create_if_absent(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """
        Create a row only when none exists, in one backend operation.

        Concurrent callers racing for the same pkid produce exactly one
        ``CREATED``; every other caller gets ``ALREADY_EXISTS`` carrying the
        winning row. The TTL of an existing row is never touched.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            data: Full row to write when absent
            ttl: Time to live in seconds, applied only on a successful create

        Returns:
            ``CREATED`` or ``ALREADY_EXISTS``
        """
        pass

    @abstractmethod
    async def replace_if(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        expected: Mapping[str, Any],
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """
        Replace a row only when its current fields match ``expected``.

        The comparison and the write happen in one backend operation, so a
        transition can never be lost to an interleaved write. ``expected``
        holds scalar field values only; every listed field must be present and
        equal. A refused transition leaves both the row and its TTL untouched.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            data: Full replacement row
            expected: Field values the current row must hold
            ttl: Time to live in seconds, applied only on a successful replace

        Returns:
            ``REPLACED``, ``CONDITION_NOT_MET`` (with the current row), or
            ``MISSING``

        Raises:
            ValueError: If ``expected`` is empty or holds a non-scalar value
        """
        pass

    @abstractmethod
    async def delete(self, table_name: str, pkid: str) -> int:
        """
        Delete table row data.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self, table_name: str, pkid: str) -> bool:
        """
        Check if table row exists.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, table_name: str, pkid: str, field: str) -> Any | None:
        """
        Get a specific field from table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update a specific field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment an integer field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to a list field in table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, table_name: str, pkid: str) -> int:
        """
        Get remaining time to live for table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, table_name: str, pkid: str, ttl: int) -> bool:
        """
        Renew time to live for table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_all(
        self,
        table_name: str,
        models: type[BaseModel] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all rows for a table.

        Args:
            table_name: Table name identifier
            models: Optional BaseModel class for deserialization

        Returns:
            List of table row data dictionaries
        """
        pass

    @abstractmethod
    async def delete_table(self, table_name: str) -> int:
        """
        Delete every row in table_name for this inbox.

        Pattern matched: {inbox}:df:{table_name}:pkid:*

        Args:
            table_name: Name of the table to wipe (must be non-empty)

        Returns:
            Count of deleted rows

        Raises:
            ValueError: If table_name is empty

        Example:
            count = await table_cache.delete_table("products")
        """
        pass

    @abstractmethod
    async def list_pkids(self, table_name: str) -> list[str]:
        """
        Return all pkids stored for this table under this inbox.

        Args:
            table_name: Name of the table

        Returns:
            List of pkid strings

        Example:
            pkids = await table_cache.list_pkids("products")
        """
        pass
