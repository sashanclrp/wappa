from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ....domain.interfaces.cache_interfaces import IStateCache
from ..ops import hget, hincrby_with_expire, hset, scan_keys
from .utils.key_factory import default_key_factory
from .utils.serde import dumps, loads
from .utils.tenant_cache import TenantCache

logger = logging.getLogger("RedisStateHandler")


class RedisStateHandler(TenantCache, IStateCache):
    user_id: str = Field(..., min_length=1)
    redis_alias: str = "state_handler"

    def _key(self, handler_name: str) -> str:
        return self.keys.handler(self.tenant, handler_name, self.user_id)

    async def get(
        self, handler_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        result = await self._get_hash(self._key(handler_name), models=models)
        if not result:
            logger.debug(
                f"Handler state not found for '{handler_name}' (user: '{self.user_id}')"
            )
        return result

    async def upsert(
        self, handler_name: str, state_data: dict[str, Any], ttl: int | None = None
    ) -> bool:
        return await self._hset_with_ttl(self._key(handler_name), state_data, ttl)

    async def get_field(self, handler_name: str, field: str) -> Any | None:
        raw_value = await hget(self._key(handler_name), field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None

    async def update_field(
        self, handler_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        key = self._key(handler_name)

        if ttl:
            return await self._hset_with_ttl(key, {field: value}, ttl)

        result = await hset(
            key, field=field, value=dumps(value), alias=self.redis_alias
        )
        return result >= 0

    async def increment_field(
        self, handler_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        new_value, expire_res = await hincrby_with_expire(
            key=self._key(handler_name),
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias,
        )

        if new_value is not None and expire_res:
            return new_value

        logger.warning(
            f"Failed to increment handler field '{field}' for '{handler_name}' (user: '{self.user_id}')"
        )
        return None

    async def append_to_list(
        self, handler_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        return await self._append_to_list_field(
            self._key(handler_name), field, value, ttl
        )

    async def exists(self, handler_name: str) -> bool:
        return await self.key_exists(self._key(handler_name))

    async def delete(self, handler_name: str) -> int:
        return await self.delete_key(self._key(handler_name))

    async def merge(
        self,
        handler_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        logger.debug(f"Upsert handler '{handler_name}' for user '{self.user_id}'")

        existing_state = await self.get(handler_name, models=models) or {}
        new_state = {
            **existing_state,
            **state_data,
            "handler_type": handler_name,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if await self.upsert(handler_name, new_state, ttl):
            logger.debug(
                f"Successfully upserted handler '{handler_name}' for user '{self.user_id}'"
            )
            return new_state

        logger.error(
            f"Failed to upsert handler '{handler_name}' for user '{self.user_id}'"
        )
        return None

    async def get_ttl(self, handler_name: str) -> int:
        return await super().get_ttl(self._key(handler_name))

    async def renew_ttl(self, handler_name: str, ttl: int) -> bool:
        return await super().renew_ttl(self._key(handler_name), ttl)

    async def delete_by_handler_prefix(self, prefix: str) -> int:
        if not prefix:
            raise ValueError("prefix must not be empty")

        pattern = (
            f"{self.tenant}:{self.keys.handler_prefix}:{prefix}*:{self.user_id}"
        )

        logger.debug(
            f"Deleting state handlers with prefix '{prefix}' for user '{self.user_id}' "
            f"(pattern: '{pattern}')"
        )

        count = await self._delete_by_pattern(pattern)

        if count > 0:
            logger.info(
                f"Deleted {count} state handler(s) with prefix '{prefix}' "
                f"for user '{self.user_id}'"
            )
        else:
            logger.debug(
                f"No state handlers found with prefix '{prefix}' for user '{self.user_id}'"
            )

        return count

    async def list_handlers(self, prefix: str | None = None) -> list[str]:
        safe_prefix = prefix or ""
        pattern = (
            f"{self.tenant}:{self.keys.handler_prefix}:{safe_prefix}*:{self.user_id}"
        )

        key_prefix = f"{self.tenant}:{self.keys.handler_prefix}:"
        key_suffix = f":{self.user_id}"

        keys = await self._scan_keys_by_pattern(pattern)
        handler_names = []
        for key in keys:
            if key.startswith(key_prefix) and key.endswith(key_suffix):
                name = key[len(key_prefix) : -len(key_suffix)]
                handler_names.append(name)

        return handler_names

    @classmethod
    async def list_users_with_handler(
        cls, tenant_id: str, handler_name: str
    ) -> list[str]:
        pattern = (
            f"{tenant_id}:{default_key_factory.handler_prefix}:{handler_name}:*"
        )
        key_prefix = (
            f"{tenant_id}:{default_key_factory.handler_prefix}:{handler_name}:"
        )

        user_ids: list[str] = []
        cursor = "0"

        try:
            while True:
                next_cursor, keys_batch = await scan_keys(
                    match_pattern=pattern,
                    cursor=cursor,
                    count=100,
                    alias="state_handler",
                )
                for key in keys_batch:
                    if key.startswith(key_prefix):
                        user_ids.append(key[len(key_prefix) :])
                if next_cursor == "0":
                    break
                cursor = next_cursor
        except Exception as e:
            logger.error(
                f"Error listing users for handler '{handler_name}' "
                f"(tenant: '{tenant_id}'): {e}",
                exc_info=True,
            )

        return user_ids
