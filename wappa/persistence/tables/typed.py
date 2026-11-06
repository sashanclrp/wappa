"""Typed convenience wrapper for inbox-scoped table caches."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from wappa.domain.interfaces.cache_interfaces import (
    ITableCache,
    TableRowTransition,
    TableTransitionResult,
)
from wappa.persistence.cache_space import build_table_name, require_non_empty


@dataclass(frozen=True, slots=True)
class TypedRowTransition[T: BaseModel]:
    """The outcome of an atomic transition, with any blocking row validated.

    ``row`` is the state the backend actually holds when the transition was
    refused — the winner of a create race, or the row that moved on before a
    conditional replace. It is ``None`` on success and on a missing row.
    """

    transition: TableRowTransition
    row: T | None = None

    @property
    def written(self) -> bool:
        """Whether this call is the one that wrote the row."""
        return self.transition in (
            TableRowTransition.CREATED,
            TableRowTransition.REPLACED,
        )


class TypedTableCache[T: BaseModel]:
    """Bind an ``ITableCache`` to one table name and Pydantic row model.

    Args:
        cache: Inbox-scoped table cache created by an ``ICacheFactory``.
        table_name: Logical table name.
        model: Pydantic model every row is validated against.
        default_ttl: TTL applied when a call does not pass one.
        cache_space: Optional host-owned namespace prefixed to the table name.
            See :mod:`wappa.persistence.cache_space`.
    """

    def __init__(
        self,
        cache: ITableCache,
        table_name: str,
        model: type[T],
        default_ttl: int | None = None,
        cache_space: str | None = None,
    ) -> None:
        self.cache = cache
        self.cache_space = cache_space
        self.table_name = build_table_name(table_name, cache_space)
        self.model = model
        self.default_ttl = default_ttl

    async def get(self, pkid: str) -> T | None:
        row = await self.cache.get(
            self.table_name,
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
        pkid = require_non_empty(pkid, "pkid")
        return await self.cache.upsert(
            self.table_name,
            pkid,
            self._validate(data),
            ttl=self._resolve_ttl(ttl),
        )

    async def create_if_absent(
        self,
        pkid: str,
        data: T | dict[str, Any],
        ttl: int | None = None,
    ) -> TypedRowTransition[T]:
        """Claim a row: exactly one concurrent caller gets ``CREATED``.

        A losing caller receives ``ALREADY_EXISTS`` together with the row that
        won, so it can act on the settled state without a follow-up read that
        might already be stale.
        """
        result = await self.cache.create_if_absent(
            self.table_name,
            require_non_empty(pkid, "pkid"),
            self._validate(data),
            ttl=self._resolve_ttl(ttl),
        )
        return self._typed(result)

    async def replace_if(
        self,
        pkid: str,
        data: T | dict[str, Any],
        expected: Mapping[str, Any],
        ttl: int | None = None,
    ) -> TypedRowTransition[T]:
        """Replace a row only while it still holds ``expected``.

        The comparison and the write are one backend operation, so a
        transition can never be lost to an interleaved write. A refused
        transition leaves the row and its TTL exactly as they were.
        """
        result = await self.cache.replace_if(
            self.table_name,
            require_non_empty(pkid, "pkid"),
            self._validate(data),
            expected,
            ttl=self._resolve_ttl(ttl),
        )
        return self._typed(result)

    async def delete(self, pkid: str) -> int:
        return await self.cache.delete(
            self.table_name,
            require_non_empty(pkid, "pkid"),
        )

    async def exists(self, pkid: str) -> bool:
        return await self.cache.exists(
            self.table_name,
            require_non_empty(pkid, "pkid"),
        )

    async def update_field(
        self,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        pkid = require_non_empty(pkid, "pkid")
        field = require_non_empty(field, "field")
        return await self.cache.update_field(
            self.table_name,
            pkid,
            field,
            value,
            ttl=self._resolve_ttl(ttl),
        )

    async def renew_ttl(self, pkid: str, ttl: int | None = None) -> bool:
        """Extend the TTL of an existing row without rewriting it."""
        resolved = self._resolve_ttl(ttl)
        if resolved is None:
            raise ValueError("renew_ttl requires a ttl or a default_ttl")
        return await self.cache.renew_ttl(
            self.table_name,
            require_non_empty(pkid, "pkid"),
            resolved,
        )

    def _typed(self, result: TableTransitionResult) -> TypedRowTransition[T]:
        row = None if result.row is None else self._validate(result.row)
        return TypedRowTransition(result.transition, row)

    def _validate(self, data: T | dict[str, Any]) -> T:
        if isinstance(data, self.model):
            return data
        return self.model.model_validate(data)

    def _resolve_ttl(self, ttl: int | None) -> int | None:
        return self.default_ttl if ttl is None else ttl
