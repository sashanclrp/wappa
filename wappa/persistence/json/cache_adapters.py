"""
JSON cache adapters that implement the ICache interface.

These adapters wrap JSON handlers to provide a uniform ICache interface
while preserving all functionality and maintaining API compatibility with Redis.
"""

from typing import Any

from pydantic import BaseModel

from ...domain.interfaces.cache_interface import ICache
from .handlers.state_handler import JSONStateHandler
from .handlers.table_handler import JSONTable
from .handlers.user_handler import JSONUser


class JSONStateCacheAdapter(ICache):
    """Adapter that makes JSONStateHandler implement ICache interface."""

    def __init__(self, tenant_id: str, user_id: str):
        self._handler = JSONStateHandler(tenant=tenant_id, user_id=user_id)
        self._default_handler_name = "cache"

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key."""
        return await self._handler.get(key, models=models)

    async def set(self, key: str, data: dict[str, Any] | BaseModel, ttl: int | None = None) -> bool:
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
        return await self._handler.get_ttl(key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        return await self._handler.renew_ttl(key, ttl=ttl)


class JSONUserCacheAdapter(ICache):
    """Adapter that makes JSONUser implement ICache interface."""

    def __init__(self, tenant_id: str, user_id: str):
        self._handler = JSONUser(tenant=tenant_id, user_id=user_id)

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key. For user cache, key is ignored as it uses user_id."""
        return await self._handler.get(models=models)

    async def set(self, key: str, data: dict[str, Any] | BaseModel, ttl: int | None = None) -> bool:
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
        return await self._handler.get_ttl(key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        return await self._handler.renew_ttl(key, ttl=ttl)


class JSONTableCacheAdapter(ICache):
    """
    Adapter that makes JSONTable implement ICache interface.
    
    Table Key Format Guide:
    Use create_table_key(table_name, pkid) to generate proper keys.
    
    Examples:
        # Good - using helper method
        key = cache.create_table_key("user_profiles", "12345")
        await cache.set(key, user_data)
        
        # Also supported - manual format
        key = "user_profiles:12345"
        await cache.set(key, user_data)
    """

    def __init__(self, tenant_id: str):
        self._handler = JSONTable(tenant=tenant_id)
    
    def create_table_key(self, table_name: str, pkid: str) -> str:
        """
        Create a properly formatted table cache key.
        
        Args:
            table_name: Name of the table (e.g., "user_profiles", "message_logs")
            pkid: Primary key ID (e.g., user_id, message_id)
            
        Returns:
            Formatted key string for use with cache methods
            
        Example:
            key = cache.create_table_key("user_profiles", "12345")
            # Returns: "user_profiles:12345"
        """
        if not table_name or not pkid:
            raise ValueError("Both table_name and pkid must be provided and non-empty")
        
        # Sanitize inputs to avoid conflicts
        safe_table_name = str(table_name).replace(":", "_")
        safe_pkid = str(pkid).replace(":", "_")
        
        return f"{safe_table_name}:{safe_pkid}"

    async def get(
        self, key: str, models: type[BaseModel] | None = None
    ) -> dict[str, Any] | None:
        """Get cached data by key. Key should be in format 'table_name:pkid'."""
        table_name, pkid = self._parse_key(key)
        return await self._handler.get(table_name, pkid, models=models)

    async def set(self, key: str, data: dict[str, Any] | BaseModel, ttl: int | None = None) -> bool:
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
        return await self._handler.get_ttl(key)

    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set time to live for a key."""
        return await self._handler.renew_ttl(key, ttl=ttl)

    def _parse_key(self, key: str) -> tuple[str, str]:
        """
        Parse key into table_name and pkid with validation.
        
        Args:
            key: Cache key in format "table_name:pkid"
            
        Returns:
            Tuple of (table_name, pkid)
            
        Raises:
            ValueError: If key format is invalid
        """
        if not key:
            raise ValueError("Key cannot be empty")
            
        if ":" not in key:
            raise ValueError(
                f"Invalid table cache key format: '{key}'. "
                f"Expected format: 'table_name:pkid'. "
                f"Use create_table_key(table_name, pkid) to generate proper keys."
            )
        
        parts = key.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid table cache key format: '{key}'. Expected exactly one ':' separator.")
            
        table_name, pkid = parts
        
        if not table_name.strip():
            raise ValueError(f"Invalid table cache key: '{key}'. Table name cannot be empty.")
            
        if not pkid.strip():
            raise ValueError(f"Invalid table cache key: '{key}'. Primary key ID cannot be empty.")
            
        return table_name.strip(), pkid.strip()