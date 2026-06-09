"""Typed convenience wrapper for inbox-scoped table caches."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from wappa.domain.interfaces.cache_interfaces import ITableCache


class TypedTableCache[T: BaseModel]:
    """Bind an ``ITableCache`` to one table name and Pydantic row model."""

    def __init__(
        self,
        cache: ITableCache,
        table_name: str,
        model: type[T],
        default_ttl: int | None = None,
    ) -> None:
        self.cache = cache
        self.table_name = self._require_non_empty(table_name, "table_name")
        self.model = model
        self.default_ttl = default_ttl

    async def get(self, pkid: str) -> T | None:
        row = await self.cache.get(
            self.table_name,
            self._require_non_empty(pkid, "pkid"),
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
        pkid = self._require_non_empty(pkid, "pkid")
        return await self.cache.upsert(
            self.table_name,
            pkid,
            self._validate(data),
            ttl=self._resolve_ttl(ttl),
        )

    async def delete(self, pkid: str) -> int:
        return await self.cache.delete(
            self.table_name,
            self._require_non_empty(pkid, "pkid"),
        )

    async def exists(self, pkid: str) -> bool:
        return await self.cache.exists(
            self.table_name,
            self._require_non_empty(pkid, "pkid"),
        )

    async def update_field(
        self,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        pkid = self._require_non_empty(pkid, "pkid")
        field = self._require_non_empty(field, "field")
        return await self.cache.update_field(
            self.table_name,
            pkid,
            field,
            value,
            ttl=self._resolve_ttl(ttl),
        )

    def _validate(self, data: T | dict[str, Any]) -> T:
        if isinstance(data, self.model):
            return data
        return self.model.model_validate(data)

    def _resolve_ttl(self, ttl: int | None) -> int | None:
        return self.default_ttl if ttl is None else ttl

    @staticmethod
    def _require_non_empty(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value
