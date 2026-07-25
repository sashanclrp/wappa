"""Versioned table cache for cheap, broad read-model invalidation.

Invalidating a whole read model normally means enumerating and deleting every
key — expensive on Redis, and impossible to do atomically while writers are
active. A version generation avoids that: every row lives under a table name
carrying a generation counter, and invalidation bumps the counter. Readers
immediately miss, writers immediately write into the new generation, and the
previous generation is orphaned.

Orphaned rows are reclaimed by TTL, so a ``default_ttl`` is required: without
one, bumped generations would linger forever.

    versions = VersionedTableCache(
        cache=factory.create_table_cache(),
        table_name="agent_directory",
        model=AgentRow,
        default_ttl=900,
        cache_space="crm",
    )

    await versions.upsert("agent-1", row)
    await versions.bump_version()      # every cached row is now unreachable
    assert await versions.get("agent-1") is None
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from wappa.domain.interfaces.cache_interfaces import ITableCache
from wappa.persistence.cache_space import (
    build_table_name,
    require_non_empty,
    validate_segment,
)

# Table holding the generation counter for every versioned table in this
# Inbox (and cache space). Kept separate from the data tables so a bump never
# competes with row writes.
VERSION_TABLE = "_wappa_table_versions"
# The stored value counts *bumps*, not generations, so a table that has never
# been invalidated needs no counter row at all: absent counter == generation 1.
VERSION_FIELD = "bumps"
FIRST_VERSION = 1

# The counter must outlive every row written under an older generation. After a
# bump, the newest possible stale row expires within one `default_ttl`, so the
# counter TTL only needs a margin above that. Backends apply their own default
# TTL to any write, so the counter TTL is always passed explicitly rather than
# left to the backend.
VERSION_TTL_FACTOR = 4
MIN_VERSION_TTL = 3600


class VersionedTableCache[T: BaseModel]:
    """A typed table cache whose rows can be invalidated by version bump.

    Args:
        cache: Inbox-scoped table cache created by an ``ICacheFactory``.
        table_name: Logical table name.
        model: Pydantic model every row is validated against.
        default_ttl: Required TTL in seconds. Also bounds how long an orphaned
            generation occupies the backend after a bump.
        cache_space: Optional host-owned namespace prefixed to the table name.

    Note:
        Every operation reads the current generation first, costing one extra
        cache read. That is what makes a bump visible across processes; a
        process-local cached version would keep serving stale rows after
        another worker invalidated them.
    """

    def __init__(
        self,
        cache: ITableCache,
        table_name: str,
        model: type[T],
        default_ttl: int,
        cache_space: str | None = None,
    ) -> None:
        if not isinstance(default_ttl, int) or default_ttl <= 0:
            raise ValueError(
                "default_ttl must be a positive number of seconds — orphaned "
                "generations are reclaimed by TTL"
            )
        self.cache = cache
        self.cache_space = cache_space
        self.logical_table_name = validate_segment(table_name, "table_name")
        self.base_table_name = build_table_name(table_name, cache_space)
        self.model = model
        self.default_ttl = default_ttl
        self._version_table = build_table_name(VERSION_TABLE, cache_space)
        self._version_ttl = max(default_ttl * VERSION_TTL_FACTOR, MIN_VERSION_TTL)

    async def current_version(self) -> int:
        """Return the active generation, defaulting to 1 when never bumped."""
        raw = await self.cache.get_field(
            self._version_table,
            self.logical_table_name,
            VERSION_FIELD,
        )
        return self._to_version(raw)

    async def bump_version(self) -> int:
        """Invalidate every cached row and return the new generation.

        Each bump refreshes the counter's own TTL, which is kept well above
        ``default_ttl``. If the counter ever did expire while orphaned rows
        were still live, the generation would fall back to ``v1`` and resurrect
        them; the margin makes that impossible, and an expiry after a long
        idle period costs only a cold cache.
        """
        bumps = await self.cache.increment_field(
            self._version_table,
            self.logical_table_name,
            VERSION_FIELD,
            increment=1,
            ttl=self._version_ttl,
        )
        if bumps is None:
            raise RuntimeError(
                f"Failed to bump cache version for table {self.logical_table_name!r}"
            )
        return self._to_version(bumps)

    @staticmethod
    def _to_version(bumps: object) -> int:
        try:
            counter = int(bumps)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            counter = 0
        return FIRST_VERSION + max(counter, 0)

    async def get(self, pkid: str) -> T | None:
        row = await self.cache.get(
            await self._table(),
            require_non_empty(pkid, "pkid"),
            models=self.model,
        )
        if row is None:
            return None
        return self._validate(row)

    async def upsert(
        self,
        pkid: str,
        data: T | dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        return await self.cache.upsert(
            await self._table(),
            require_non_empty(pkid, "pkid"),
            self._validate(data),
            ttl=self._resolve_ttl(ttl),
        )

    async def delete(self, pkid: str) -> int:
        return await self.cache.delete(
            await self._table(),
            require_non_empty(pkid, "pkid"),
        )

    async def exists(self, pkid: str) -> bool:
        return await self.cache.exists(
            await self._table(),
            require_non_empty(pkid, "pkid"),
        )

    async def update_field(
        self,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        return await self.cache.update_field(
            await self._table(),
            require_non_empty(pkid, "pkid"),
            require_non_empty(field, "field"),
            value,
            ttl=self._resolve_ttl(ttl),
        )

    async def renew_ttl(self, pkid: str, ttl: int | None = None) -> bool:
        """Extend a row's TTL inside the current generation."""
        return await self.cache.renew_ttl(
            await self._table(),
            require_non_empty(pkid, "pkid"),
            self._resolve_ttl(ttl),
        )

    async def current_table_name(self) -> str:
        """Physical table name backing the active generation."""
        return await self._table()

    async def _table(self) -> str:
        return f"{self.base_table_name}@v{await self.current_version()}"

    def _validate(self, data: T | dict[str, Any]) -> T:
        if isinstance(data, self.model):
            return data
        return self.model.model_validate(data)

    def _resolve_ttl(self, ttl: int | None) -> int:
        return self.default_ttl if ttl is None else ttl
