"""
Cache adapters that make Redis handlers implement the ICache interface.

These adapters wrap the existing Redis handlers to provide a uniform ICache interface
while preserving all the existing functionality.
"""

from typing import Any

from pydantic import BaseModel

from ...domain.interfaces.cache_interface import ICache
from .redis_handler.state_handler import RedisStateHandler
from .redis_handler.table import RedisTable
from .redis_handler.user import RedisUser


class RedisStateCacheAdapter(ICache):
    """Adapter that makes RedisStateHandler implement ICache interface."""

    def __init__(
        self, tenant_id: str, user_id: str, redis_alias: str = "state_handler"
    ):
        self._handler = RedisStateHandler(
            tenant=tenant_id, user_id=user_id, redis_alias=redis_alias
        )
        self._default_handler_name = "cache"

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key."""
        return await self._handler.get(key, models=models)

    async def set(self, key: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """Set cached data with optional TTL."""
        return await self._handler.upsert(key, data, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        result = await self._handler.delete(key)
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return await self._handler.exists(key)

    async def get_field(self, key: str, field: str) -> Any | None:
        """Get a specific field from cached hash data."""
        return await self._handler.get_field(key, field)

    async def set_field(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Set a specific field in cached hash data."""
        return await self._handler.update_field(key, field, value, ttl=ttl)

    async def increment_field(
        self, key: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """Atomically increment an integer field."""
        return await self._handler.increment_field(key, field, increment, ttl=ttl)

    async def append_to_list(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to a list field."""
        return await self._handler.append_to_list(key, field, value, ttl=ttl)

    async def get_ttl(self, key: str) -> int:
        """Get remaining time to live for a key."""
        handler_key = self._handler._key(key)
        return await self._handler.get_ttl(handler_key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        handler_key = self._handler._key(key)
        return await self._handler.renew_ttl(handler_key, ttl=ttl)


class RedisUserCacheAdapter(ICache):
    """Adapter that makes RedisUser implement ICache interface."""

    def __init__(self, tenant_id: str, user_id: str, redis_alias: str = "users"):
        self._handler = RedisUser(
            tenant=tenant_id, user_id=user_id, redis_alias=redis_alias
        )

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key. For user cache, key is ignored as it uses user_id."""
        return await self._handler.get(models=models)

    async def set(self, key: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """Set cached data with optional TTL."""
        return await self._handler.upsert(data, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        result = await self._handler.delete()
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return await self._handler.exists()

    async def get_field(self, key: str, field: str) -> Any | None:
        """Get a specific field from cached hash data."""
        return await self._handler.get_field(field)

    async def set_field(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Set a specific field in cached hash data."""
        return await self._handler.update_field(field, value, ttl=ttl)

    async def increment_field(
        self, key: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """Atomically increment an integer field."""
        return await self._handler.increment_field(field, increment, ttl=ttl)

    async def append_to_list(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to a list field."""
        return await self._handler.append_to_list(field, value, ttl=ttl)

    async def get_ttl(self, key: str) -> int:
        """Get remaining time to live for a key."""
        handler_key = self._handler._key()
        return await self._handler.get_ttl(handler_key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        handler_key = self._handler._key()
        return await self._handler.renew_ttl(handler_key, ttl=ttl)


class RedisTableCacheAdapter(ICache):
    """Adapter that makes RedisTable implement ICache interface."""

    def __init__(self, tenant_id: str, redis_alias: str = "table"):
        self._handler = RedisTable(tenant=tenant_id, redis_alias=redis_alias)

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key. Key should be in format 'table_name:pkid'."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.get(table_name, pkid, models=models)

    async def set(self, key: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """Set cached data with optional TTL."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.upsert(table_name, pkid, data, ttl=ttl)

    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        table_name, pkid = self._parse_key(key)
        result = await self._handler.delete(table_name, pkid)
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.exists(table_name, pkid)

    async def get_field(self, key: str, field: str) -> Any | None:
        """Get a specific field from cached hash data."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.get_field(table_name, pkid, field)

    async def set_field(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Set a specific field in cached hash data."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.update_field(table_name, pkid, field, value, ttl=ttl)

    async def increment_field(
        self, key: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """Atomically increment an integer field."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.increment_field(
            table_name, pkid, field, increment, ttl=ttl
        )

    async def append_to_list(
        self, key: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to a list field."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.append_to_list(
            table_name, pkid, field, value, ttl=ttl
        )

    async def get_ttl(self, key: str) -> int:
        """Get remaining time to live for a key."""
        table_name, pkid = self._parse_key(key)
        handler_key = self._handler._key(table_name, pkid)
        return await self._handler.get_ttl(handler_key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        table_name, pkid = self._parse_key(key)
        handler_key = self._handler._key(table_name, pkid)
        return await self._handler.renew_ttl(handler_key, ttl=ttl)

    def _parse_key(self, key: str) -> tuple[str, str]:
        """Parse key into table_name and pkid."""
        if ":" in key:
            table_name, pkid = key.split(":", 1)
            return table_name, pkid
        else:
            # If no separator, use key as both table_name and pkid
            return key, key
