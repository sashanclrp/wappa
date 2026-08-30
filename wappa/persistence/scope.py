"""Table Cache Scope rules and the reserved System Scope.

Table Cache is the one cache family whose namespace is a general
``context_id``. Three meanings are recognised:

- System: the exact constant :data:`SYSTEM_SCOPE`, owned by Wappa.
- Host-defined business scope: an identifier the Host Application chooses.
- Inbox: the Wappa-encoded ``InboxRef.cache_namespace``.

The scopes are siblings. Nothing falls back from one to another and nothing
cascades between them.
"""

from __future__ import annotations

from typing import Final

from wappa.domain.interfaces.cache_interfaces import ITableCache

SYSTEM_SCOPE: Final[str] = "__system__"


def validate_context_id(value: object) -> str:
    """Return ``value`` when it can serve as a Table Cache ``context_id``."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("context_id must be a non-empty string")
    return value


# The pre-v0.27 spellings of the Table Cache namespace parameter. They are
# rejected rather than aliased: the grilling session settled that v0.27 is a
# clean contract break, and two live names for one argument is exactly the
# ambiguity the rename removed.
_RENAMED_KEYWORDS: Final[tuple[str, ...]] = ("inbox_id", "inbox")


def resolve_table_context_id(context_id: object, **renamed: object) -> str:
    """Return the Table Cache Scope, rejecting pre-v0.27 keywords with guidance.

    A caller still passing ``inbox_id=`` or ``inbox=`` gets a ``TypeError``
    that names the rename and the migration, instead of an opaque
    "unexpected keyword argument".
    """
    for keyword in _RENAMED_KEYWORDS:
        if renamed.get(keyword) is not None:
            raise TypeError(
                f"Table Cache no longer accepts {keyword}=. Wappa v0.27.0 renamed "
                "the Table Cache namespace parameter to context_id, because Table "
                "Cache is the one cache family whose scope may be the System "
                "Scope, a Host-defined business scope, or an Inbox namespace. "
                f"Replace {keyword}=<value> with context_id=<value>; the stored "
                "keys are unchanged, so no cache migration is needed. Every other "
                "cache family still takes inbox_id. See "
                "docs/migration/v0.27.0-multi-inbox.md."
            )
    if context_id is None:
        raise TypeError("Table Cache requires a context_id")
    return validate_context_id(context_id)


def is_system_scope(context_id: str) -> bool:
    """Whether ``context_id`` is exactly the reserved System Scope."""
    return context_id == SYSTEM_SCOPE


def create_system_table_cache(cache_type: str) -> ITableCache:
    """Build an ``ITableCache`` bound to the reserved System Scope.

    Reuses the configured persistence backend and, on Redis, the existing
    ``table`` pool. The result knows nothing about what it stores; Wappa
    services such as the Inbox Directory layer their records on top.
    """
    normalized = cache_type.strip().lower()
    if normalized == "redis":
        from .redis.redis_handler.table import RedisTable

        return RedisTable(SYSTEM_SCOPE, redis_alias="table")
    if normalized == "memory":
        from .memory.handlers.table_handler import MemoryTable

        return MemoryTable(SYSTEM_SCOPE)
    if normalized == "json":
        from .json.handlers.table_handler import JSONTable

        return JSONTable(SYSTEM_SCOPE)
    raise ValueError(
        f"Unsupported cache_type: {cache_type}. "
        "Supported types: 'redis', 'json', 'memory'"
    )


__all__ = [
    "SYSTEM_SCOPE",
    "create_system_table_cache",
    "is_system_scope",
    "resolve_table_context_id",
    "validate_context_id",
]
