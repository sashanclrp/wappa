#!/usr/bin/env python3
"""List one Inbox's Wappa Redis keys (read-only): key, type, TTL.

Usage (run from the app folder so its .env is found):
    uv run python ../../wappa/scripts/redis_inspect.py --platform instagram --inbox 1784...
    uv run python ../../wappa/scripts/redis_inspect.py --platform whatsapp --inbox 1014... --user 5731...
    ... --values          # also print values (secret-named fields redacted)

Patterns come from Wappa itself: the Inbox namespace is
``InboxRef.cache_namespace`` (``<platform>__<inbox_id>``) and the per-cache
patterns from ``KeyFactory``. Every Wappa pool database is scanned
(users=0, state_handler=1, table=2, expiry=3, ai_state=4), plus the Inbox
Directory row in the System Scope table. With ``--user`` only that User's
user/state/aistate keys are listed (tables and expiry triggers are not
User-scoped). Only SCAN, TYPE, TTL and, with ``--values``, read commands are
issued. The Redis URL comes from ``--redis-url``, then REDIS_URL (env or
.env); its password is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.password:
        host = parts.hostname or ""
        netloc = f"{parts.username or ''}:***@{host}" + (
            f":{parts.port}" if parts.port else ""
        )
        parts = parts._replace(netloc=netloc)
    return urlunsplit(parts)


def _base_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if path.rsplit("/", 1)[-1].isdigit():
        path = path.rsplit("/", 1)[0]
    return urlunsplit(parts._replace(path=path))


def patterns(platform: str, inbox_id: str, user_id: str | None) -> dict[str, list[str]]:
    """Pool alias → SCAN patterns, built with Wappa's own key builders."""
    from wappa.domain.inbox import InboxRef
    from wappa.persistence.inbox_directory import PRIMARY_TABLE
    from wappa.persistence.redis.redis_handler.utils.key_factory import KeyFactory
    from wappa.persistence.scope import SYSTEM_SCOPE
    from wappa.schemas.core.types import PlatformType

    ref = InboxRef(platform=PlatformType(platform.lower()), inbox_id=inbox_id)
    ns = ref.cache_namespace
    keys = KeyFactory()
    directory_row = keys.glob_escape(keys.table(SYSTEM_SCOPE, PRIMARY_TABLE, ns))
    if user_id is not None:
        return {
            "users": [
                keys.user_pattern(ns, user_id),
                f"{keys.user_pattern(ns, user_id)}:*",
            ],
            "state_handler": [keys.handler_pattern(ns, user_id=user_id)],
            "ai_state": [keys.aistate_pattern(ns, user_id=user_id)],
        }
    everything = f"{keys.glob_escape(ns)}:*"
    return {
        "users": [everything],
        "state_handler": [everything],
        "table": [everything, directory_row],
        "expiry": [everything],
        "ai_state": [everything],
    }


def _value(client: Any, key: str, kind: str) -> Any:
    from wappa.core.inbound.payload_capture import redact_payload

    if kind == "string":
        raw = client.get(key)
        try:
            return redact_payload(json.loads(raw))
        except (TypeError, ValueError):
            return redact_payload(raw)
    if kind == "hash":
        return redact_payload(client.hgetall(key))
    if kind == "list":
        return redact_payload(client.lrange(key, 0, 49))
    if kind == "set":
        return redact_payload(sorted(client.smembers(key))[:50])
    if kind == "zset":
        return redact_payload(client.zrange(key, 0, 49, withscores=True))
    return f"<{kind}: not shown>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List one Inbox's Wappa Redis keys (read-only)."
    )
    parser.add_argument("--platform", required=True, help="whatsapp | instagram")
    parser.add_argument(
        "--inbox",
        required=True,
        help="inbox_id (WhatsApp phone_number_id, IG account ID)",
    )
    parser.add_argument("--user", help="only this User's keys")
    parser.add_argument("--values", action="store_true", help="print values (redacted)")
    parser.add_argument("--redis-url", help="default: REDIS_URL from env or .env")
    parser.add_argument("--env-file", default=".env", help="dotenv file (default .env)")
    args = parser.parse_args(argv)

    load_dotenv(args.env_file, override=False)
    url = args.redis_url or os.getenv("REDIS_URL")
    if not url:
        raise SystemExit("error: no Redis URL (--redis-url or REDIS_URL)")

    import redis

    from wappa.persistence.redis.redis_client import POOL_DB_MAPPING

    base = _base_url(url)
    plan = patterns(args.platform, args.inbox, args.user)
    print(
        f"redis {_safe_url(base)} · {args.platform}/{args.inbox}"
        + (f" · user {args.user}" if args.user else "")
    )
    total = 0
    for alias, pats in plan.items():
        db = POOL_DB_MAPPING[alias]  # type: ignore[index]
        client = redis.Redis.from_url(f"{base}/{db}", decode_responses=True)
        found: set[str] = set()
        for pattern in pats:
            found.update(client.scan_iter(match=pattern, count=500))
        print(f"\n[db {db} {alias}] {len(found)} key(s)  patterns: {', '.join(pats)}")
        for key in sorted(found):
            kind = str(client.type(key))
            ttl = client.ttl(key)
            ttl_text = (
                "no-expiry" if ttl == -1 else ("gone" if ttl == -2 else f"{ttl}s")
            )
            print(f"  {key}  type={kind}  ttl={ttl_text}")
            if args.values:
                value = _value(client, key, kind)
                print(
                    f"    = {json.dumps(value, ensure_ascii=False, default=str)[:2000]}"
                )
        total += len(found)
        client.close()
    print(f"\n{total} key(s) total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
