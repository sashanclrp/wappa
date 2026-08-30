from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, cast

from pydantic import BaseModel

from ....domain.interfaces.cache_interfaces import (
    ITableCache,
    TableRowTransition,
    TableTransitionResult,
)
from ...row_conditions import condition_tokens, require_full_row
from ...scope import resolve_table_context_id
from ..ops import eval_script, hget, hincrby_with_expire
from ..redis_client import PoolAlias
from .utils.inbox_cache import InboxCache
from .utils.serde import dumps_hash, loads, loads_hash

logger = logging.getLogger("RedisTable")

# Both scripts answer with {status, current_row}: 1 wrote, 0 was blocked by the
# current row (returned so the caller need not re-read it), 2 found no row.
_WROTE = 1
_BLOCKED = 0
_ABSENT = 2

_CREATE_IF_ABSENT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return {0, redis.call('HGETALL', KEYS[1])}
end
local row = {}
for i = 2, #ARGV do row[#row + 1] = ARGV[i] end
redis.call('HSET', KEYS[1], unpack(row))
redis.call('EXPIRE', KEYS[1], ARGV[1])
return {1, {}}
"""

# ARGV: ttl, expected-pair count, expected field/value pairs, replacement pairs.
# A refused transition returns before EXPIRE, so the stored TTL survives it.
_REPLACE_IF = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return {2, {}}
end
local expected = tonumber(ARGV[2])
for i = 1, expected do
  if redis.call('HGET', KEYS[1], ARGV[2 + i * 2 - 1]) ~= ARGV[2 + i * 2] then
    return {0, redis.call('HGETALL', KEYS[1])}
  end
end
local row = {}
for i = 3 + expected * 2, #ARGV do row[#row + 1] = ARGV[i] end
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], unpack(row))
redis.call('EXPIRE', KEYS[1], ARGV[1])
return {1, {}}
"""


def _row_payload(data: dict[str, Any] | BaseModel) -> list[str]:
    """Flatten a full row into the field/value arguments HSET expects."""
    encoded = dumps_hash(require_full_row(data))
    return [token for pair in encoded.items() for token in pair]


class RedisTable(InboxCache, ITableCache):
    """
    Repository for table data management (generic DataFrames/rows).

    The first key segment is a Table Cache ``context_id``: the reserved System
    Scope, a Host-defined business scope, or an Inbox namespace. Construct it
    positionally or with ``context_id=``; the former ``inbox=`` keyword is gone
    and raises ``TypeError`` rather than silently binding a stale name.

    Extracted from RedisHandler SECTION: Table Data Management:
    - set_table_data() -> upsert()
    - get_table_data() -> get()
    - get_field() -> get_field()
    - increment_table_data_field() -> increment_field()
    - append_to_table_data_list_field() -> append_to_list()
    - table_data_exists() -> exists()
    - delete_table_data() -> delete()
    - create_or_update_table_field() -> update_field()
    - find_table_by_field() -> find_by_field()
    - delete_all_tables_by_pkid() -> delete_all_by_pkid()

    Single Responsibility: Table/DataFrame data management only
    """

    redis_alias: PoolAlias = "table"

    def __init__(
        self,
        context_id: str | None = None,
        *,
        redis_alias: PoolAlias = "table",
        ttl_default: int = 86400,
        **renamed: object,
    ) -> None:
        """Bind this repository to one Table Cache Scope.

        ``**renamed`` traps the pre-v0.27 ``inbox_id=`` / ``inbox=`` keywords
        so they fail with migration guidance rather than an opaque
        "unexpected keyword argument".
        """
        super().__init__(
            inbox=resolve_table_context_id(context_id, **renamed),
            redis_alias=redis_alias,
            ttl_default=ttl_default,
        )

    @property
    def context_id(self) -> str:
        """The Table Cache Scope this repository is bound to."""
        return self.inbox

    def _key(self, table_name: str, pkid: str) -> str:
        """Build table key using KeyFactory"""
        return self.keys.table(self.inbox, table_name, pkid)

    # ---- Public API extracted from RedisHandler Table methods ---------------
    async def get(
        self,
        table_name: str,
        pkid: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get full table row data (was get_table_data)

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            models: Optional BaseModel class for full object reconstruction
                   e.g., TableRow (will automatically handle nested RowMetadata, RowConfig)
        """
        key = self._key(table_name, pkid)
        result = await self._get_hash(key, models=models)
        if not result:
            logger.debug(f"Table data not found for '{table_name}:{pkid}'")
        return result

    async def upsert(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """Set table row data (Redis HSET upsert behavior)"""
        key = self._key(table_name, pkid)
        return await self._hset_with_ttl(key, data, ttl)

    async def create_if_absent(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """Create a row only when absent (single EVAL, no read-then-write)."""
        payload = _row_payload(data)
        status, row = await self._transition(
            _CREATE_IF_ABSENT,
            self._key(table_name, pkid),
            [ttl or self.ttl_default, *payload],
        )
        if status == _WROTE:
            return TableTransitionResult(TableRowTransition.CREATED)
        return TableTransitionResult(TableRowTransition.ALREADY_EXISTS, row)

    async def replace_if(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any] | BaseModel,
        expected: Mapping[str, Any],
        ttl: int | None = None,
    ) -> TableTransitionResult:
        """Replace a row only when its current fields match (single EVAL)."""
        conditions = condition_tokens(expected)
        payload = _row_payload(data)
        flattened = [token for pair in conditions.items() for token in pair]
        status, row = await self._transition(
            _REPLACE_IF,
            self._key(table_name, pkid),
            [ttl or self.ttl_default, len(conditions), *flattened, *payload],
        )
        if status == _WROTE:
            return TableTransitionResult(TableRowTransition.REPLACED)
        if status == _ABSENT:
            return TableTransitionResult(TableRowTransition.MISSING)
        return TableTransitionResult(TableRowTransition.CONDITION_NOT_MET, row)

    async def _transition(
        self,
        script: str,
        key: str,
        args: Sequence[str | int | float],
    ) -> tuple[int, dict[str, Any] | None]:
        """Run a transition script and decode its {status, row} reply."""
        reply = cast(
            "list[Any]",
            await eval_script(script, [key], args, alias=self.redis_alias),
        )
        status = int(reply[0])
        flat = reply[1] if len(reply) > 1 else []
        if not flat:
            return status, None
        raw = dict(zip(flat[0::2], flat[1::2], strict=True))
        return status, cast("dict[str, Any]", loads_hash(raw))

    async def get_field(self, table_name: str, pkid: str, field: str) -> Any | None:
        """Get a specific field from table row data"""
        key = self._key(table_name, pkid)
        raw_value = await hget(key, field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None

    async def update_field(
        self, table_name: str, pkid: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Update single field in table row"""
        key = self._key(table_name, pkid)
        return await self._hset_with_ttl(key, {field: value}, ttl)

    async def increment_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """Atomically increment integer field (was increment_table_data_field)"""
        key = self._key(table_name, pkid)

        new_value, expire_res = await hincrby_with_expire(
            key=key,
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias,
        )

        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(
                f"Failed to increment table field '{field}' for '{table_name}:{pkid}'"
            )
            return None

    async def append_to_list(
        self, table_name: str, pkid: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to list field (was append_to_table_data_list_field)"""
        key = self._key(table_name, pkid)
        return await self._append_to_list_field(key, field, value, ttl)

    async def exists(self, table_name: str, pkid: str) -> bool:
        """Check if table row exists (was table_data_exists)"""
        key = self._key(table_name, pkid)
        return await self.key_exists(key)

    async def delete(self, table_name: str, pkid: str) -> int:
        """Delete table row (was delete_table_data)"""
        key = self._key(table_name, pkid)
        return await self.delete_key(key)

    async def find_by_field(
        self,
        table_name: str,
        field: str,
        value: Any,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Find first row in table where field matches value (was find_table_by_field)

        Args:
            table_name: Name of the table
            field: Field name to search
            value: Value to match
            models: Optional BaseModel class for full object reconstruction
        """
        pattern = self.keys.table_pattern(self.inbox, table_name)
        return await self._find_by_field(pattern, field, value, models=models)

    async def delete_all_by_pkid(self, pkid: str) -> int:
        """
        Delete all table rows across all tables with same pkid (was delete_all_tables_by_pkid)

        This creates a pattern that matches any table with the given pkid:
        inbox:df:*:pkid:safe_pkid
        """
        pattern = self.keys.table_pattern(self.inbox, pkid=pkid)

        logger.info(
            f"Deleting all table data with pkid '{pkid}' (pattern: '{pattern}')"
        )
        return await self._delete_by_pattern(pattern)

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
        return await self._get_ttl(key)

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
        return await self._renew_ttl(key, ttl)

    async def delete_table(self, table_name: str) -> int:
        if not table_name:
            raise ValueError("table_name must not be empty")

        pattern = self.keys.table_pattern(self.inbox, table_name)

        logger.debug(
            f"Deleting all rows in table '{table_name}' for inbox '{self.inbox}' "
            f"(pattern: '{pattern}')"
        )

        count = await self._delete_by_pattern(pattern)

        if count > 0:
            logger.info(
                f"Deleted {count} row(s) from table '{table_name}' "
                f"for inbox '{self.inbox}'"
            )
        else:
            logger.debug(
                f"No rows found in table '{table_name}' for inbox '{self.inbox}'"
            )

        return count

    async def list_pkids(self, table_name: str) -> list[str]:
        pattern = self.keys.table_pattern(self.inbox, table_name)
        pkid_marker = f":{self.keys.pk_marker}:"

        keys = await self._scan_keys_by_pattern(pattern)
        pkids = []
        for key in keys:
            idx = key.rfind(pkid_marker)
            if idx >= 0:
                pkids.append(key[idx + len(pkid_marker) :])

        return pkids

    async def get_all(
        self,
        table_name: str,
        models: type[BaseModel] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get all rows for a table using Redis SCAN.

        Args:
            table_name: Table name identifier
            models: Optional BaseModel class for deserialization

        Returns:
            List of table row data dictionaries
        """
        from ..ops import scan_keys

        pattern = self.keys.table_pattern(self.inbox, table_name)
        results = []
        cursor = 0

        try:
            while True:
                next_cursor, keys_batch = await scan_keys(
                    match_pattern=pattern,
                    cursor=cursor,
                    count=100,
                    alias=self.redis_alias,
                )

                for key in keys_batch:
                    data = await self._get_hash(key, models=models)
                    if data:
                        results.append(data)

                if next_cursor == 0:
                    break
                cursor = next_cursor

            logger.debug(f"Retrieved {len(results)} rows from table '{table_name}'")
            return results

        except Exception as e:
            logger.error(
                f"Error getting all rows from table '{table_name}': {e}", exc_info=True
            )
            return []
