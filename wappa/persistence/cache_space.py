"""Cache space naming for inbox-scoped table caches.

Wappa scopes cache keys by Inbox — that is the runtime identity and it is
applied by the ``ICacheFactory`` that creates the underlying cache. A **cache
space** is an optional second segment owned by the host application: a short
label separating unrelated read models that happen to share a table name
inside the same Inbox (``billing:invoices`` vs ``crm:invoices``).

Wappa never invents a cache space. It is passed explicitly by the host, and
when omitted the table name is used unchanged so existing keys keep working.
"""

from __future__ import annotations

SEPARATOR = ":"

# Separator characters are reserved for composition, so a caller cannot smuggle
# extra key segments through a space or table name.
_RESERVED = (SEPARATOR, "@")


def build_table_name(table_name: str, cache_space: str | None = None) -> str:
    """Compose the physical table name for ``table_name`` inside ``cache_space``.

    Args:
        table_name: Logical table name, e.g. ``invoices``.
        cache_space: Optional host-owned namespace, e.g. ``billing``.

    Returns:
        ``"{cache_space}:{table_name}"`` when a space is given, otherwise
        ``table_name`` unchanged.

    Raises:
        ValueError: If either value is blank or contains a reserved character.
    """
    table = validate_segment(table_name, "table_name")
    if cache_space is None:
        return table
    space = validate_segment(cache_space, "cache_space")
    return f"{space}{SEPARATOR}{table}"


def validate_segment(value: str, name: str) -> str:
    """Validate one key segment, returning it stripped."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    candidate = value.strip()
    for reserved in _RESERVED:
        if reserved in candidate:
            raise ValueError(f"{name} must not contain {reserved!r}")
    return candidate


def require_non_empty(value: str, name: str) -> str:
    """Reject a blank value, returning it unchanged (not stripped).

    Unlike :func:`validate_segment`, this does not forbid the reserved
    separator characters — it is used for row-level identifiers (``pkid``,
    field names) that are not composed into a key segment themselves.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value
