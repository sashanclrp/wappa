"""AI agent state cache interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class IAIStateCache(ABC):
    """
    Interface for AI agent state cache operations.

    State shared among AI agents for context and coordination.
    Agent identity is established via agent_name parameter.

    Key pattern: {inbox}:aistate:{agent_name}:{user_id}
    Example: "wappa:aistate:summarizer:user123"
    """

    @abstractmethod
    async def get(
        self, agent_name: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """
        Get AI agent state data.

        Args:
            agent_name: Name of the AI agent
            models: Optional BaseModel class for full object reconstruction

        Returns:
            AI agent state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def upsert(
        self, agent_name: str, data: dict[str, Any] | BaseModel, ttl: int | None = None
    ) -> bool:
        """
        Create or update AI agent state data.

        Args:
            agent_name: Name of the AI agent
            data: State data to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, agent_name: str) -> int:
        """
        Delete AI agent state data.

        Args:
            agent_name: Name of the AI agent

        Returns:
            Number of keys deleted (1 if deleted, 0 if didn't exist)
        """
        pass

    @abstractmethod
    async def exists(self, agent_name: str) -> bool:
        """
        Check if AI agent state exists.

        Args:
            agent_name: Name of the AI agent

        Returns:
            True if exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_field(self, agent_name: str, field: str) -> Any | None:
        """
        Get specific field from AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_field(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Update specific field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name
            value: New value
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def increment_field(
        self, agent_name: str, field: str, increment: int = 1, ttl: int | None = None
    ) -> int | None:
        """
        Atomically increment integer field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name
            increment: Amount to increment by
            ttl: Time to live in seconds

        Returns:
            New value after increment or None on error
        """
        pass

    @abstractmethod
    async def append_to_list(
        self, agent_name: str, field: str, value: Any, ttl: int | None = None
    ) -> bool:
        """
        Append value to list field in AI agent state.

        Args:
            agent_name: Name of the AI agent
            field: Field name containing list
            value: Value to append
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_ttl(self, agent_name: str) -> int:
        """
        Get remaining TTL for AI agent state.

        Args:
            agent_name: Name of the AI agent

        Returns:
            Remaining TTL in seconds, -1 if no expiry, -2 if doesn't exist
        """
        pass

    @abstractmethod
    async def renew_ttl(self, agent_name: str, ttl: int) -> bool:
        """
        Renew TTL for AI agent state.

        Args:
            agent_name: Name of the AI agent
            ttl: New time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
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
            agent_name: Name of the AI agent
            state_data: New state data to merge
            ttl: Optional TTL override
            models: Optional mapping for BaseModel deserialization

        Returns:
            Final merged state or None on failure
        """
        pass

    @abstractmethod
    async def delete_all_for_user(self) -> int:
        """
        Delete every AI agent state entry for this cache's user_id,
        regardless of agent name.

        Pattern matched: {inbox}:aistate:*:{user_id}

        Returns:
            Count of deleted entries
        """
        pass

    @abstractmethod
    async def delete_by_agent_prefix(self, prefix: str) -> int:
        """
        Delete every agent entry whose name starts with prefix, scoped to
        this cache's user_id.

        Pattern matched: {inbox}:aistate:{prefix}*:{user_id}

        Args:
            prefix: Agent name prefix (must be non-empty)

        Returns:
            Count of deleted entries

        Raises:
            ValueError: If prefix is empty

        Example:
            count = await ai_state_cache.delete_by_agent_prefix("summarizer-")
        """
        pass
