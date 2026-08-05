"""Canonical encoding for conditional table-row comparisons.

A conditional row replacement compares what a caller *expects* a field to hold
against what a backend *currently stores*. Each backend stores that field
differently — Redis keeps a serialized hash field, the memory store keeps the
live Python object, the JSON store keeps its file-serialized form — so a naive
``==`` gives three different answers for the same row.

Every adapter therefore folds both sides through :func:`condition_token` before
comparing. The Redis hash encoding is the canonical form because it is the only
one that has to survive a round trip through a wire protocol; the other
backends borrow it so that ``Status.PENDING``, ``"pending"``, and the string a
Redis hash actually holds all compare equal.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# The Redis hash encoder owns this format; conditions reuse it rather than
# maintaining a second encoder that could silently drift from stored values.
from wappa.persistence.redis.redis_handler.utils.serde import dumps

# Conditions match one scalar field value. Containers are rejected because
# their encoded form depends on ordering, which no backend guarantees.
_COMPARABLE_SCALARS = (str, bool, int, float, Enum, datetime, date, time, UUID)


def condition_token(value: Any) -> str:
    """Return the canonical comparison token for one expected field value."""
    if value is not None and not isinstance(value, _COMPARABLE_SCALARS):
        raise ValueError(
            "Row conditions compare scalar field values only; got "
            f"{type(value).__name__}. Condition on a scalar discriminator "
            "(status, revision, owner id) instead."
        )
    return dumps(value)


def condition_tokens(expected: Mapping[str, Any]) -> dict[str, str]:
    """Validate an expectation map and return its encoded tokens."""
    if not expected:
        raise ValueError(
            "A conditional replacement needs at least one expected field — use "
            "upsert for an unconditional write"
        )
    return {field: condition_token(value) for field, value in expected.items()}


def row_predicate(expected: Mapping[str, Any]) -> Callable[[Any], bool]:
    """Build the "does the stored row still permit this transition" test.

    Used by the backends that hold rows as live objects. Redis compares the
    same tokens inside Lua instead, so the answer does not depend on which
    backend a Host Application configured.
    """
    tokens = condition_tokens(expected)

    def matches(row: Any) -> bool:
        if not isinstance(row, Mapping):
            return False
        return all(
            field in row and condition_token(row[field]) == token
            for field, token in tokens.items()
        )

    return matches


def require_full_row(data: dict[str, Any] | BaseModel) -> dict[str, Any] | BaseModel:
    """Reject an empty row: a transition writes a whole row or nothing."""
    if isinstance(data, BaseModel):
        return data
    if not data:
        raise ValueError(
            "An atomic row transition writes a whole row; an empty row would "
            "erase it instead"
        )
    return data


__all__ = [
    "condition_token",
    "condition_tokens",
    "require_full_row",
    "row_predicate",
]
