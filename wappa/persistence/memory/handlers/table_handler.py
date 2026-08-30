"""
Memory Table handler - mirrors Redis table handler functionality.

Provides table cache operations using in-memory storage.
"""

import logging
from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel

from ....domain.interfaces.cache_interfaces import (
    ITableCache,
    TableRowTransition,
    TableTransitionResult,
)
from ...row_conditions import require_full_row, row_predicate
from ...scope import resolve_table_context_id
from ..storage_manager import storage_manager
from .utils.key_factory import default_key_factory

logger = logging.getLogger("MemoryTable")


class MemoryTable(ITableCache):
    """
    Memory-based table cache handler.

    Mirrors RedisTable functionality using in-memory storage.
    Maintains the same API for seamless cache backend switching.
    """

    def __init__(self, context_id: str | None = None, **renamed: object):
        """
        Initialize Memory table handler.

        Args:
            context_id: Table Cache Scope — the reserved System Scope, a
                Host-defined business scope, or an Inbox namespace.
            **renamed: Traps the pre-v0.27 ``inbox_id=`` / ``inbox=`` keywords
                so they fail with migration guidance instead of an opaque
                "unexpected keyword argument".
        """
        self.context_id = resolve_table_context_id(context_id, **renamed)
        self.keys = default_key_factory

    def _key(self, table_name: str, pkid: str) -> str:
        """Build table key using KeyFactory (same as Redis)."""
        return self.keys.table(self.context_id, table_name, pkid)

    # ---- Public API matching RedisTable ----
    async def get(
        self,
        table_name: str,
        pkid: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get table row data.

        Args:
            table_name: Table name
            pkid: Primary key ID
            models: Optional BaseModel class for deserialization

        Returns:
            Table row data or None if not found
        """
        key = self._key(table_name, pkid)
        return cast(
            "dict[str, Any] | None",
            await storage_manager.get("tables", self.context_id, None, key, models),
        )

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
            table_name: Table name
            pkid: Primary key ID
            data: Data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key(table_name, pkid)
        return await storage_manager.set(
            "tables", self.context_id, None, key, data, ttl
        )

    async def create_if_absent(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """Create a row only when absent, under the namespace lock."""
        created, existing = await storage_manager.create_if_absent(
            "tables",
            self.context_id,
            None,
            self._key(table_name, pkid),
            require_full_row(data),
            ttl,
        )
        if created:
            return TableTransitionResult(TableRowTransition.CREATED)
        return TableTransitionResult(TableRowTransition.ALREADY_EXISTS, existing)

    async def replace_if(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        expected: Mapping[str, Any],
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """Replace a row only when the stored one still matches ``expected``."""
        matches = row_predicate(expected)
        outcome, current = await storage_manager.replace_if(
            "tables",
            self.context_id,
            None,
            self._key(table_name, pkid),
            require_full_row(data),
            matches,
            ttl,
        )
        if outcome == "replaced":
            return TableTransitionResult(TableRowTransition.REPLACED)
        if outcome == "missing":
            return TableTransitionResult(TableRowTransition.MISSING)
        return TableTransitionResult(TableRowTransition.CONDITION_NOT_MET, current)

    async def delete(self, table_name: str, pkid: str) -> int:
        """
        Delete table row data.

        Args:
            table_name: Table name
            pkid: Primary key ID

        Returns:
            1 if deleted, 0 if didn't exist
        """
        key = self._key(table_name, pkid)
        success = await storage_manager.delete("tables", self.context_id, None, key)
        return 1 if success else 0

    async def exists(self, table_name: str, pkid: str) -> bool:
        """
        Check if table row exists.

        Args:
            table_name: Table name
            pkid: Primary key ID

        Returns:
            True if exists, False otherwise
        """
        key = self._key(table_name, pkid)
        return await storage_manager.exists("tables", self.context_id, None, key)

    async def get_field(self, table_name: str, pkid: str, field: str) -> Any | None:
        """
        Get a specific field from table row.

        Args:
            table_name: Table name
            pkid: Primary key ID
            field: Field name

        Returns:
            Field value or None if not found
        """
        row_data = await self.get(table_name, pkid)
        if row_data is None:
            return None

        if isinstance(row_data, dict):
            return row_data.get(field)
        else:
            # BaseModel instance
            return getattr(row_data, field, None)

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
            table_name: Table name
            pkid: Primary key ID
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        row_data = await self.get(table_name, pkid)
        if row_data is None:
            row_data = {}

        if isinstance(row_data, BaseModel):
            row_data = row_data.model_dump()

        row_data[field] = value
        return await self.upsert(table_name, pkid, row_data, ttl)

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
            table_name: Table name
            pkid: Primary key ID
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        row_data = await self.get(table_name, pkid)
        if row_data is None:
            row_data = {}

        if isinstance(row_data, BaseModel):
            row_data = row_data.model_dump()

        current_value = row_data.get(field, 0)
        if not isinstance(current_value, int | float):
            logger.warning(
                f"Cannot increment non-numeric field '{field}': {current_value}"
            )
            return None

        new_value = int(current_value) + increment
        row_data[field] = new_value

        success = await self.upsert(table_name, pkid, row_data, ttl)
        return new_value if success else None

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
            table_name: Table name
            pkid: Primary key ID
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        row_data = await self.get(table_name, pkid)
        if row_data is None:
            row_data = {}

        if isinstance(row_data, BaseModel):
            row_data = row_data.model_dump()

        current_list = row_data.get(field, [])
        if not isinstance(current_list, list):
            current_list = []

        current_list.append(value)
        row_data[field] = current_list

        return await self.upsert(table_name, pkid, row_data, ttl)

    async def get_ttl(self, table_name: str, pkid: str) -> int:
        """
        Get remaining time to live for table row.

        Args:
            table_name: Table name identifier
            pkid: Primary key ID

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        key = self._key(table_name, pkid)
        return await storage_manager.get_ttl("tables", self.context_id, None, key)

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
        key = self._key(table_name, pkid)
        return await storage_manager.set_ttl("tables", self.context_id, None, key, ttl)

    async def get_all(
        self,
        table_name: str,
        models: type[BaseModel] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all rows for a table by scanning keys matching the table pattern.

        Args:
            table_name: Table name identifier
            models: Optional BaseModel class for deserialization

        Returns:
            List of table row data dictionaries
        """
        results: list[dict[str, Any]] = []
        key_prefix = self.keys.table(self.context_id, table_name, "")

        try:
            all_keys = await storage_manager.get_all_keys(
                "tables", self.context_id, None
            )

            for key, value in all_keys.items():
                if key.startswith(key_prefix):
                    if models is not None and isinstance(value, dict):
                        results.append(
                            cast("dict[str, Any]", models.model_validate(value))
                        )
                    else:
                        results.append(value)

            logger.debug(f"Retrieved {len(results)} rows from table '{table_name}'")
            return results

        except Exception as e:
            logger.error(
                f"Error getting all rows from table '{table_name}': {e}", exc_info=True
            )
            return []

    async def delete_table(self, table_name: str) -> int:
        """Delete every row in a table for this inbox."""
        if not table_name:
            raise ValueError("table_name must be non-empty")

        deleted = 0
        key_prefix = self.keys.table(self.context_id, table_name, "")
        all_keys = await storage_manager.get_all_keys("tables", self.context_id, None)

        for key in all_keys:
            if key.startswith(key_prefix):
                success = await storage_manager.delete(
                    "tables", self.context_id, None, key
                )
                if success:
                    deleted += 1

        return deleted

    async def list_pkids(self, table_name: str) -> list[str]:
        """Return all pkids stored for a table under this inbox."""
        if not table_name:
            raise ValueError("table_name must be non-empty")

        key_prefix = self.keys.table(self.context_id, table_name, "")
        all_keys = await storage_manager.get_all_keys("tables", self.context_id, None)
        return sorted(
            key.removeprefix(key_prefix)
            for key in all_keys
            if key.startswith(key_prefix)
        )
