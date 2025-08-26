"""
Tables repository interface.

Defines contract for table data operations (generic DataFrames/rows).
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from .base_repository import IBaseRepository


class ITablesRepository(IBaseRepository, ABC):
    """
    Interface for table data repository operations.

    Provides contract for generic table/DataFrame data management,
    following the existing RedisTable functionality patterns.
    """

    @abstractmethod
    async def get_table_data(
        self,
        table_name: str,
        pkid: str,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get full table row data.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            models: Optional BaseModel class for full object reconstruction

        Returns:
            Table row data dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_table_data(
        self,
        table_name: str,
        pkid: str,
        data: dict[str, Any],
        ttl: int | None = None,
    ) -> bool:
        """
        Set table row data (upsert behavior).

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            data: Data to store
            ttl: Optional TTL in seconds

        Returns:
            True if stored successfully
        """
        pass

    @abstractmethod
    async def get_table_field(
        self, table_name: str, pkid: str, field: str
    ) -> Any | None:
        """
        Get a specific field from table row data.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            field: Field name to retrieve

        Returns:
            Field value or None if not found
        """
        pass

    @abstractmethod
    async def update_table_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Update single field in table row.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            field: Field name to update
            value: New field value
            ttl: Optional TTL in seconds

        Returns:
            True if updated successfully
        """
        pass

    @abstractmethod
    async def increment_table_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        increment: int = 1,
        ttl: int | None = None,
    ) -> int | None:
        """
        Atomically increment integer field.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            field: Field name to increment
            increment: Amount to increment by (default: 1)
            ttl: Optional TTL in seconds

        Returns:
            New field value after increment, or None if failed
        """
        pass

    @abstractmethod
    async def append_to_table_list_field(
        self,
        table_name: str,
        pkid: str,
        field: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Append value to list field.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier
            field: Field name containing the list
            value: Value to append
            ttl: Optional TTL in seconds

        Returns:
            True if appended successfully
        """
        pass

    @abstractmethod
    async def table_data_exists(self, table_name: str, pkid: str) -> bool:
        """
        Check if table row exists.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier

        Returns:
            True if table row exists
        """
        pass

    @abstractmethod
    async def delete_table_data(self, table_name: str, pkid: str) -> int:
        """
        Delete table row.

        Args:
            table_name: Name of the table
            pkid: Primary key identifier

        Returns:
            Number of keys deleted
        """
        pass

    @abstractmethod
    async def find_table_by_field(
        self,
        table_name: str,
        field: str,
        value: Any,
        models: type[BaseModel] | None = None,
    ) -> dict[str, Any] | None:
        """
        Find first row in table where field matches value.

        Args:
            table_name: Name of the table
            field: Field name to search
            value: Value to match
            models: Optional BaseModel class for full object reconstruction

        Returns:
            First matching row data or None if not found
        """
        pass

    @abstractmethod
    async def delete_all_tables_by_pkid(self, pkid: str) -> int:
        """
        Delete all table rows across all tables with same pkid.

        Args:
            pkid: Primary key identifier

        Returns:
            Number of keys deleted
        """
        pass
