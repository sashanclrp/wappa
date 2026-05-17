"""
Database-backed inbox credential store.

The host application owns the ``wappa_inboxes`` table and its migrations.
Wappa reads the table through the supplied async session factory and keeps
hot-path credentials in Redis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Field, SQLModel

from wappa.domain.interfaces.inbox_credential_store import (
    IInboxCredentialStore,
    InboxCredentials,
    InboxNotFoundError,
)

type DBSessionFactory = Callable[[], AbstractAsyncContextManager[Any]]


class WappaInbox(SQLModel, table=True):
    """
    Optional SQLModel read model for host-owned inbox credential storage.

    Host applications may import this model for table creation or ignore it
    and provide their own migration that matches the same columns.
    """

    __tablename__ = "wappa_inboxes"

    inbox_id: str = Field(primary_key=True)
    platform: str = Field(default="whatsapp")
    access_token: str
    platform_account_id: str | None = None
    is_active: bool = Field(default=True)


class DatabaseInboxCredentialStore(IInboxCredentialStore):
    """Multi-inbox credential store with Redis cache and DB fallback."""

    _REDIS_CLIENT_METHODS = ("hgetall", "hset")

    def __init__(
        self,
        db_session_factory: DBSessionFactory,
        redis_manager: Any,
        *,
        cache_ttl: int = 300,
        redis_alias: str = "table",
    ) -> None:
        self._db_session_factory = db_session_factory
        self._redis_manager = redis_manager
        self._cache_ttl = cache_ttl
        self._redis_alias = redis_alias

    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        cached = await self._get_cached_credentials(inbox_id)
        if cached is not None:
            return cached

        credentials = await self._get_database_credentials(inbox_id)
        await self._cache_credentials(credentials)
        return credentials

    async def validate_inbox(self, inbox_id: str) -> bool:
        try:
            await self.get_credentials(inbox_id)
            return True
        except InboxNotFoundError:
            return False

    async def invalidate_cache(self, inbox_id: str) -> None:
        redis = await self._get_redis()
        await redis.delete(self._cache_key(inbox_id))

    async def _get_cached_credentials(self, inbox_id: str) -> InboxCredentials | None:
        redis = await self._get_redis()
        cached = await redis.hgetall(self._cache_key(inbox_id))
        if not cached:
            return None

        normalized = self._normalize_mapping(cached)
        if normalized.get("is_active", "").lower() != "true":
            return None

        access_token = normalized.get("access_token")
        if not access_token:
            return None

        return InboxCredentials(
            inbox_id=inbox_id,
            access_token=access_token,
            platform_account_id=normalized.get("platform_account_id") or None,
        )

    async def _get_database_credentials(self, inbox_id: str) -> InboxCredentials:
        async with self._db_session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT inbox_id, access_token, platform_account_id
                    FROM wappa_inboxes
                    WHERE inbox_id = :inbox_id
                      AND is_active = TRUE
                    LIMIT 1
                    """
                ),
                {"inbox_id": inbox_id},
            )
            row = result.mappings().first()

        if row is None:
            raise InboxNotFoundError(inbox_id)

        return InboxCredentials(
            inbox_id=str(row["inbox_id"]),
            access_token=str(row["access_token"]),
            platform_account_id=row["platform_account_id"],
        )

    async def _cache_credentials(self, credentials: InboxCredentials) -> None:
        redis = await self._get_redis()
        key = self._cache_key(credentials.inbox_id)
        await redis.hset(
            key,
            mapping={
                "access_token": credentials.access_token,
                "platform_account_id": credentials.platform_account_id or "",
                "platform": "whatsapp",
                "is_active": "true",
                "cached_at": datetime.now(UTC).isoformat(),
            },
        )
        await redis.expire(key, self._cache_ttl)

    async def _get_redis(self) -> Any:
        if all(
            hasattr(self._redis_manager, name) for name in self._REDIS_CLIENT_METHODS
        ):
            return self._redis_manager

        for accessor_name in ("get_client", "get"):
            accessor = getattr(self._redis_manager, accessor_name, None)
            if accessor is not None:
                return await accessor(self._redis_alias)

        raise TypeError(
            "redis_manager must be a Redis client or expose get_client()/get()"
        )

    @staticmethod
    def _cache_key(inbox_id: str) -> str:
        return f"inbox:{inbox_id}:credentials"

    @staticmethod
    def _normalize_mapping(mapping: Mapping[Any, Any]) -> dict[str, str]:
        return {
            (k.decode() if isinstance(k, bytes) else str(k)): (
                v.decode() if isinstance(v, bytes) else str(v)
            )
            for k, v in mapping.items()
        }
