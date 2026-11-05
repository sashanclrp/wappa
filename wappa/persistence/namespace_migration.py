"""One-off rename of pre-0.34 WhatsApp cache keys to the qualified namespace.

Wappa 0.33 and earlier wrote WhatsApp Inbox data under the raw
``phone_number_id`` (``<pnid>:state:...``); 0.34 qualifies every Platform
(``whatsapp__<pnid>:state:...``). This module renames the old keys in place.

Safety rules:

- The caller names the WhatsApp ``phone_number_id`` values. Nothing is
  guessed from key shapes, because Table Cache also accepts Host-defined
  ``context_id`` values that may be numeric.
- Dry run unless ``apply=True``.
- Redis ``RENAMENX`` keeps each key's TTL and never overwrites an existing
  qualified key; such keys are reported as conflicts and left untouched.
- Inbox Directory rows (``__system__``) are not migrated: Wappa clears that
  cache at startup and reloads it from the Host's source.

Run it while no 0.33 worker is writing, before starting 0.34.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from wappa.domain.inbox.identity import InboxRef

JSON_CACHE_FOLDERS = ("users", "tables", "states", "ai_states")
_PNID = re.compile(r"^\d+$")


@dataclass
class NamespaceMigrationReport:
    """What was (or, in a dry run, would be) renamed."""

    applied: bool
    renamed: list[tuple[str, str]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def _validated(phone_number_ids: Iterable[str]) -> list[str]:
    ids = sorted({p.strip() for p in phone_number_ids if p and p.strip()})
    if not ids:
        raise ValueError("Name at least one WhatsApp phone_number_id")
    bad = [p for p in ids if not _PNID.fullmatch(p)]
    if bad:
        raise ValueError(f"phone_number_id values must be digits only: {bad}")
    return ids


def _qualified(phone_number_id: str) -> str:
    return InboxRef.whatsapp(phone_number_id).cache_namespace


async def migrate_redis_namespaces(
    base_url: str,
    phone_number_ids: Iterable[str],
    *,
    apply: bool = False,
    databases: Iterable[int] | None = None,
) -> NamespaceMigrationReport:
    """Rename ``<pnid>:*`` to ``whatsapp__<pnid>:*`` in every Wappa database."""
    import redis.asyncio as redis

    from wappa.persistence.redis.redis_client import POOL_DB_MAPPING

    ids = _validated(phone_number_ids)
    dbs = sorted(set(databases if databases is not None else POOL_DB_MAPPING.values()))
    report = NamespaceMigrationReport(applied=apply)
    for db in dbs:
        client = redis.from_url(f"{base_url.rstrip('/')}/{db}", decode_responses=True)
        try:
            for pnid in ids:
                new_prefix = _qualified(pnid)
                async for key in client.scan_iter(match=f"{pnid}:*", count=500):
                    new_key = f"{new_prefix}{key[len(pnid) :]}"
                    label = (f"db{db}:{key}", f"db{db}:{new_key}")
                    if not apply:
                        if await client.exists(new_key):
                            report.conflicts.append(label[1])
                        else:
                            report.renamed.append(label)
                        continue
                    if await client.renamenx(key, new_key):
                        report.renamed.append(label)
                    else:
                        report.conflicts.append(label[1])
        finally:
            await client.aclose()
    return report


def migrate_json_namespaces(
    cache_root: Path,
    phone_number_ids: Iterable[str],
    *,
    apply: bool = False,
) -> NamespaceMigrationReport:
    """Rename ``<pnid>_*.json`` cache files to ``whatsapp__<pnid>_*.json``."""
    ids = _validated(phone_number_ids)
    report = NamespaceMigrationReport(applied=apply)
    for folder in JSON_CACHE_FOLDERS:
        directory = cache_root / folder
        if not directory.is_dir():
            continue
        for pnid in ids:
            for path in sorted(directory.glob(f"{pnid}_*.json")):
                target = path.with_name(f"{_qualified(pnid)}{path.name[len(pnid) :]}")
                if target.exists():
                    report.conflicts.append(str(target))
                    continue
                report.renamed.append((str(path), str(target)))
                if apply:
                    path.rename(target)
    return report


__all__ = [
    "NamespaceMigrationReport",
    "migrate_json_namespaces",
    "migrate_redis_namespaces",
]
