"""Meta payload schema drift: tolerate on input, report loudly (ADR-0010).

Models that parse Meta's webhook payloads accept fields they do not model
(``extra="allow"``), so an additive Meta change never turns into a 400 that
makes Meta retry and drop the event. After parsing, :func:`report_schema_drift`
walks the model tree and logs each unmodelled field once per process, without
its value (it may hold personal data).

Set ``WAPPA_STRICT_META_SCHEMA=1`` (the test suite does) to raise
:class:`MetaSchemaDriftError` instead, so drift in fixtures fails CI.

Wappa's own Universal Webhook contracts stay ``extra="forbid"``: they are
Wappa's output, not Meta's input.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from logging import Logger
from typing import Any

from pydantic import BaseModel

STRICT_SCHEMA_ENV = "WAPPA_STRICT_META_SCHEMA"
_reported: set[tuple[str, str]] = set()


class MetaSchemaDriftError(ValueError):
    """A Meta payload carried fields Wappa does not model (strict mode only)."""


def strict_schema_enabled() -> bool:
    return os.getenv(STRICT_SCHEMA_ENV, "").strip().lower() in {"1", "true", "yes"}


def unmodelled_fields(model: BaseModel) -> list[str]:
    """``Model.field`` names of every extra field anywhere in the tree."""
    found: list[str] = []
    seen: set[int] = set()

    def walk(value: Any) -> None:
        if isinstance(value, BaseModel):
            if id(value) in seen:
                return
            seen.add(id(value))
            if getattr(type(value), "drift_exempt", False):
                return  # permissive on purpose (app-registered field value)
            for name in value.model_extra or {}:
                found.append(f"{type(value).__name__}.{name}")
            for field_name in type(value).model_fields:
                walk(getattr(value, field_name, None))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(model)
    return sorted(set(found))


def report_schema_drift(
    model: BaseModel, *, platform: str, logger: Logger | Any
) -> list[str]:
    """Log unmodelled fields once per process; raise only in strict mode."""
    return report_unmodelled(unmodelled_fields(model), platform=platform, logger=logger)


def report_unmodelled(
    fields: Iterable[str], *, platform: str, logger: Logger | Any
) -> list[str]:
    fields = sorted(set(fields))
    for field in fields:
        if (platform, field) not in _reported:
            _reported.add((platform, field))
            logger.warning(
                "META_SCHEMA_DRIFT platform=%s field=%s: Meta sent a field Wappa "
                "does not model yet; the event was processed (value not logged)",
                platform,
                field,
            )
    if fields and strict_schema_enabled():
        raise MetaSchemaDriftError(
            f"{platform} payload has unmodelled fields: {', '.join(fields)}"
        )
    return fields


__all__ = [
    "STRICT_SCHEMA_ENV",
    "MetaSchemaDriftError",
    "report_schema_drift",
    "report_unmodelled",
    "strict_schema_enabled",
    "unmodelled_fields",
]
