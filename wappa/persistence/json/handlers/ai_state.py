"""
JSON AI State handler - mirrors Redis AI state handler functionality.

Provides AI agent state cache operations using JSON file storage.
"""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ....domain.interfaces.cache_interfaces import IAIStateCache
from ..storage_manager import storage_manager
from .utils.key_factory import default_key_factory

logger = logging.getLogger("JSONAIState")


class JSONAIState(IAIStateCache):
    """
    JSON-based AI state cache handler.

    Mirrors RedisAIState functionality using file-based JSON storage.
    Maintains the same API for seamless cache backend switching.

    Stores data in {project_root}/cache/ai_states/ directory.
    """

    def __init__(self, tenant: str, user_id: str):
        """
        Initialize JSON AI state handler.

        Args:
            tenant: Tenant identifier
            user_id: User identifier
        """
        if not tenant or not user_id:
            raise ValueError(
                f"Missing required parameters: tenant={tenant}, user_id={user_id}"
            )

        self.tenant = tenant
        self.user_id = user_id
        self.keys = default_key_factory

    def _key(self, agent_name: str) -> str:
        """Build AI state key using KeyFactory (same as Redis)."""
        return self.keys.aistate(self.tenant, agent_name, self.user_id)

    # ---- Public API matching RedisAIState ----
    async def get(
        self, agent_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get AI agent state data.

        Args:
            agent_name: AI agent name
            models: Optional BaseModel class for deserialization

        Returns:
            AI agent state data or None if not found
        """
        key = self._key(agent_name)
        return await storage_manager.get(
            "ai_states", self.tenant, self.user_id, key, models
        )

    async def upsert(
        self,
        agent_name: str,
        data: dict[str, Any] | BaseModel,
        ttl: int | None = None,
    ) -> bool:
        """
        Create or update AI agent state data.

        Args:
            agent_name: AI agent name
            data: State data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        key = self._key(agent_name)
        return await storage_manager.set(
            "ai_states", self.tenant, self.user_id, key, data, ttl
        )

    async def delete(self, agent_name: str) -> int:
        """
        Delete AI agent state data.

        Args:
            agent_name: AI agent name

        Returns:
            1 if deleted, 0 if didn't exist
        """
        key = self._key(agent_name)
        success = await storage_manager.delete(
            "ai_states", self.tenant, self.user_id, key
        )
        return 1 if success else 0

    async def exists(self, agent_name: str) -> bool:
        """
        Check if AI agent state exists.

        Args:
            agent_name: AI agent name

        Returns:
            True if exists, False otherwise
        """
        key = self._key(agent_name)
        return await storage_manager.exists("ai_states", self.tenant, self.user_id, key)

    async def get_field(self, agent_name: str, field: str) -> Any | None:
        """
        Get a specific field from AI agent state.

        Args:
            agent_name: AI agent name
            field: Field name

        Returns:
            Field value or None if not found
        """
        state_data = await self.get(agent_name)
        if state_data is None:
            return None

        if isinstance(state_data, dict):
            return state_data.get(field)
        else:
            # BaseModel instance
            return getattr(state_data, field, None)

    async def update_field(
        self,
        agent_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update a specific field in AI agent state.

        Args:
            agent_name: AI agent name
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        state_data = await self.get(agent_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        state_data[field] = value
        return await self.upsert(agent_name, state_data, ttl)

    async def increment_field(
        self,
        agent_name: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment an integer field in AI agent state.

        Args:
            agent_name: AI agent name
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        state_data = await self.get(agent_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        current_value = state_data.get(field, 0)
        if not isinstance(current_value, int | float):
            logger.warning(
                f"Cannot increment non-numeric field '{field}': {current_value}"
            )
            return None

        new_value = int(current_value) + increment
        state_data[field] = new_value

        success = await self.upsert(agent_name, state_data, ttl)
        return new_value if success else None

    async def append_to_list(
        self,
        agent_name: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to a list field in AI agent state.

        Args:
            agent_name: AI agent name
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        state_data = await self.get(agent_name)
        if state_data is None:
            state_data = {}

        if isinstance(state_data, BaseModel):
            state_data = state_data.model_dump()

        current_list = state_data.get(field, [])
        if not isinstance(current_list, list):
            current_list = []

        current_list.append(value)
        state_data[field] = current_list

        return await self.upsert(agent_name, state_data, ttl)

    async def get_ttl(self, agent_name: str) -> int:
        """
        Get remaining time to live for AI agent state.

        Args:
            agent_name: AI agent name identifier

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        key = self._key(agent_name)
        return await storage_manager.get_ttl(
            "ai_states", self.tenant, self.user_id, key
        )

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
        return await storage_manager.set_ttl(
            "ai_states", self.tenant, self.user_id, key, ttl
        )

    async def merge(
        self,
        agent_name: str,
        state_data: dict[str, Any],
        ttl: int | None = None,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Merge new data with existing AI agent state.

        Args:
            agent_name: AI agent name
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization

        Returns:
            Final merged state or None on failure
        """
        # Get existing state with optional BaseModel deserialization
        existing_state = await self.get(agent_name, models=models) or {}

        if isinstance(existing_state, BaseModel):
            existing_state = existing_state.model_dump()

        # Merge new data with existing
        new_state = {
            **existing_state,
            **state_data,
            "agent_type": agent_name,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Save merged state
        success = await self.upsert(agent_name, new_state, ttl)
        return new_state if success else None
