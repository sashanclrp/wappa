"""Explicit migration of live, qualified Expiry Keys into the recovery index."""

from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from redis.asyncio import Redis

from wappa.domain.inbox.identity import InboxRef

from .expiry_index import RedisExpiryIndex
from .redis_client import POOL_DB_MAPPING
from .redis_handler.utils.key_factory import KeyFactory


@dataclass
class ExpiryMigrationReport:
    applied: bool
    scanned: int = 0
    eligible: int = 0
    indexed: int = 0
    already_indexed: int = 0
    expired: int = 0
    persistent: int = 0
    invalid: int = 0
    conflict: int = 0

    def to_dict(self) -> dict[str, bool | int]:
        return asdict(self)


def _expiry_url(url: str, database: int) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise ValueError("An explicit redis:// or rediss:// URL is required")
    if database < 0:
        raise ValueError("Redis database must be nonnegative")
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query) if key != "db"]
    )
    return urlunsplit(parsed._replace(path=f"/{database}", query=query, fragment=""))


async def migrate_expiry_index(
    redis_url: str,
    *,
    apply: bool = False,
    database: int = POOL_DB_MAPPING["expiry"],
) -> ExpiryMigrationReport:
    """SCAN only trigger-shaped keys; never change TTLs, values or existing records.

    Reports counts without exposing identifiers, payloads or connection secrets.
    Stop old timer writers before applying; expired unindexed keys cannot be recovered.
    """
    client: Redis = Redis.from_url(
        _expiry_url(redis_url, database), decode_responses=False
    )
    report = ExpiryMigrationReport(applied=apply)
    keys = KeyFactory()
    try:
        index = RedisExpiryIndex(client)
        # SCAN can return duplicates. Count each key once, including in dry runs.
        seen: set[bytes | str] = set()
        async for raw in client.scan_iter(match="*:EXPTRIGGER:*", count=100):
            if raw in seen:
                continue
            seen.add(raw)
            report.scanned += 1
            try:
                key = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                parsed = keys.parse_trigger(key)
                if parsed is None or not parsed[1] or not parsed[2]:
                    raise ValueError("Invalid Expiry Key")
                InboxRef.from_cache_namespace(parsed[0])
            except ValueError:
                report.invalid += 1
                continue
            outcome = await index.index_existing(key, apply=apply)
            setattr(report, outcome, getattr(report, outcome) + 1)
    finally:
        await client.aclose()
    return report
