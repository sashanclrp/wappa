from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from ....domain.interfaces.cache_interfaces import IAIStateCache
from ..ops import hget, hincrby_with_expire, hset
from .utils.serde import dumps, loads
from .utils.tenant_cache import TenantCache

logger = logging.getLogger("RedisAIState")


class RedisAIState(TenantCache, IAIStateCache):
    user_id: str = Field(..., min_length=1)
    redis_alias: str = "ai_state"  # Uses ai_state pool (db=4)

    def _key(self, agent_name: str) -> str:
        return self.keys.aistate(self.tenant, agent_name, self.user_id)

    async def get(
        self, agent_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        result = await self._get_hash(self._key(agent_name), models=models)
        if not result:
            logger.debug(
                f"AI agent state not found for '{agent_name}' (user: '{self.user_id}')"
            )
        return result

    async def upsert(
        self,
        agent_name: str,
        state_data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        return await self._hset_with_ttl(self._key(agent_name), state_data, ttl)

    async def get_field(self, agent_name: str, field: str) -> Any | None:
        raw_value = await hget(self._key(agent_name), field, alias=self.redis_alias)
        return loads(raw_value) if raw_value is not None else None

    async def update_field(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        key = self._key(agent_name)

        if ttl:
            return await self._hset_with_ttl(key, {field: value}, ttl)

        result = await hset(
            key, field=field, value=dumps(value), alias=self.redis_alias
        )
        return result >= 0

    async def increment_field(
        self, agent_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        new_value, expire_res = await hincrby_with_expire(
            key=self._key(agent_name),
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias,
        )

        if new_value is not None and expire_res:
            return new_value

        logger.warning(
            f"Failed to increment AI agent field '{field}' for '{agent_name}' (user: '{self.user_id}')"
        )
        return None

    async def append_to_list(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        return await self._append_to_list_field(
            self._key(agent_name), field, value, ttl
        )

    async def exists(self, agent_name: str) -> bool:
        return await self.key_exists(self._key(agent_name))

    async def delete(self, agent_name: str) -> int:
        return await self.delete_key(self._key(agent_name))

    async def merge(
        self,
        agent_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        logger.debug(f"Upsert AI agent '{agent_name}' for user '{self.user_id}'")

        existing_state = await self.get(agent_name, models=models) or {}
        new_state = {
            **existing_state,
            **state_data,
            "agent_type": agent_name,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if await self.upsert(agent_name, new_state, ttl):
            logger.debug(
                f"Successfully upserted AI agent '{agent_name}' for user '{self.user_id}'"
            )
            return new_state

        logger.error(
            f"Failed to upsert AI agent '{agent_name}' for user '{self.user_id}'"
        )
        return None

    async def get_ttl(self, agent_name: str) -> int:
        return await super().get_ttl(self._key(agent_name))

    async def renew_ttl(self, agent_name: str, ttl: int) -> bool:
        return await super().renew_ttl(self._key(agent_name), ttl)
