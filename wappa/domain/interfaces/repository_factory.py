"""
Repository factory interface.

Defines contract for creating context-aware repository instances.
"""

from abc import ABC, abstractmethod

from .expiry_repository import IExpiryRepository
from .pubsub_repository import IPubSubRepository
from .shared_state_repository import ISharedStateRepository
from .state_repository import IStateRepository
from .tables_repository import ITablesRepository
from .user_repository import IUserRepository


class IRepositoryFactory(ABC):
    """
    Interface for creating context-aware repository instances.

    Ensures all repositories are bound to the correct tenant and user context.
    """

    @abstractmethod
    def create_user_repository(self, tenant_id: str, user_id: str) -> IUserRepository:
        """
        Create user repository with context binding.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            Context-bound user repository instance
        """
        pass

    @abstractmethod
    def create_state_repository(self, tenant_id: str, user_id: str) -> IStateRepository:
        """
        Create state repository with context binding.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            Context-bound state repository instance
        """
        pass

    @abstractmethod
    def create_shared_state_repository(
        self, tenant_id: str, user_id: str
    ) -> ISharedStateRepository:
        """
        Create shared state repository with context binding.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier

        Returns:
            Context-bound shared state repository instance
        """
        pass

    @abstractmethod
    def create_expiry_repository(self, tenant_id: str) -> IExpiryRepository:
        """
        Create expiry repository with context binding.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Context-bound expiry repository instance
        """
        pass

    @abstractmethod
    def create_pubsub_repository(
        self, tenant_id: str, user_id: str | None = None
    ) -> IPubSubRepository:
        """
        Create pub/sub repository with context binding.

        Args:
            tenant_id: Tenant identifier
            user_id: Optional user identifier (for user-specific channels)

        Returns:
            Context-bound pub/sub repository instance
        """
        pass

    @abstractmethod
    def create_tables_repository(self, tenant_id: str) -> ITablesRepository:
        """
        Create tables repository with context binding.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Context-bound tables repository instance
        """
        pass
