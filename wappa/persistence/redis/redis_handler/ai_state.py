from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ....domain.interfaces.cache_interfaces import IAIStateCache
from ..ops import hget, hincrby_with_expire, hset
from .utils.serde import dumps
from .utils.tenant_cache import TenantCache

logger = logging.getLogger("RedisAIState")


class RedisAIState(TenantCache, IAIStateCache):
    """
    Repository for AI agent state management.

    Manages state shared among AI agents for context coordination.
    Single Responsibility: AI agent state management only

    Key pattern: {tenant}:aistate:{agent_name}:{user_id}
    Example: "wappa:aistate:summarizer:user123"

    Example usage:
        ai_state = RedisAIState(tenant="wappa", user_id="user123")
        await ai_state.upsert("summarizer", {"context": "...", "count": 5})
        state = await ai_state.get("summarizer")
    """

    user_id: str = Field(..., min_length=1)
    redis_alias: str = "ai_state"  # Uses ai_state pool (db=4)

    def _key(self, agent_name: str) -> str:
        """Build AI state key using KeyFactory"""
        return self.keys.aistate(self.tenant, agent_name, self.user_id)

    # ---- Public API implementing IAIStateCache ------------------------------
    async def get(
        self, agent_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get full AI agent state hash.

        Args:
            agent_name: Name of the AI agent
            models: Optional BaseModel class for full object reconstruction
        """
        key = self._key(agent_name)
        result = await self._get_hash(key, models=models)
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
        """Set AI agent state, overwriting existing (Redis HSET upsert behavior)"""
        key = self._key(agent_name)
        return await self._hset_with_ttl(key, state_data, ttl)

    async def get_field(self, agent_name: str, field: str) -> Any | None:
        """Get specific field from AI agent state"""
        key = self._key(agent_name)
        return await hget(key, field, alias=self.redis_alias)

    async def update_field(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Update single field in AI agent state"""
        key = self._key(agent_name)

        if ttl:
            # Use inherited method with TTL renewal
            return await self._hset_with_ttl(key, {field: value}, ttl)
        else:
            # Use simple hset without TTL renewal
            serialized_value = dumps(value)
            result = await hset(
                key, field=field, value=serialized_value, alias=self.redis_alias
            )
            return result >= 0

    async def increment_field(
        self, agent_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """Atomically increment integer field in AI agent state"""
        key = self._key(agent_name)

        new_value, expire_res = await hincrby_with_expire(
            key=key,
            field=field,
            increment=increment,
            ttl=ttl or self.ttl_default,
            alias=self.redis_alias,
        )

        if new_value is not None and expire_res:
            return new_value
        else:
            logger.warning(
                f"Failed to increment AI agent field '{field}' for '{agent_name}' (user: '{self.user_id}')"
            )
            return None

    async def append_to_list(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """Append value to list field in AI agent state"""
        key = self._key(agent_name)
        return await self._append_to_list_field(key, field, value, ttl)

    async def exists(self, agent_name: str) -> bool:
        """Check if AI agent state exists"""
        key = self._key(agent_name)
        return await self.key_exists(key)

    async def delete(self, agent_name: str) -> int:
        """Delete AI agent state"""
        key = self._key(agent_name)
        return await self.delete_key(key)

    async def merge(
        self,
        agent_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Merge new data with existing AI agent state and save.
        Returns the final merged state or None on failure.

        Args:
            agent_name: Name of the AI agent
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization when reading existing state
        """
        logger.debug(f"Upsert AI agent '{agent_name}' for user '{self.user_id}'")

        # Get existing state with optional BaseModel deserialization
        existing_state = await self.get(agent_name, models=models) or {}

        # Merge new data with existing
        new_state = {
            **existing_state,
            **state_data,
            "agent_type": agent_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Save merged state
        success = await self.upsert(agent_name, new_state, ttl)

        if success:
            logger.debug(
                f"Successfully upserted AI agent '{agent_name}' for user '{self.user_id}'"
            )
            return new_state
        else:
            logger.error(
                f"Failed to upsert AI agent '{agent_name}' for user '{self.user_id}'"
            )
            return None

    async def get_ttl(self, agent_name: str) -> int:
        """
        Get remaining time to live for AI agent state.

        Args:
            agent_name: AI agent name identifier

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        key = self._key(agent_name)
        return await super().get_ttl(key)

    async def renew_ttl(self, agent_name: str, ttl: int) -> bool:
        """
        Renew time to live for AI agent state.

        Args:
            agent_name: AI agent name identifier
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key(agent_name)
        return await super().renew_ttl(key, ttl)
