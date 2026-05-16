"""
Inbox credential store interface.

Defines the contract for resolving credentials for a specific inbox.
Implementations can be backed by env vars, database, or any external store.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class InboxCredentials:
    """Resolved credentials for a specific inbox."""

    inbox_id: str
    access_token: str
    platform_account_id: str | None = None


class InboxNotFoundError(Exception):
    """Raised when an inbox_id is not recognized by the credential store."""

    def __init__(self, inbox_id: str):
        self.inbox_id = inbox_id
        super().__init__(f"Inbox not found: {inbox_id}")


class IInboxCredentialStore(ABC):
    """
    Strategy interface for resolving inbox credentials.

    Implementations:
    - SettingsInboxCredentialStore (default): single inbox from env vars
    - Future: database/Redis-cached credential store for multi-inbox
    """

    @abstractmethod
    async def get_credentials(self, inbox_id: str) -> InboxCredentials:
        """
        Resolve credentials for an inbox.

        Args:
            inbox_id: The inbox identifier (e.g., WhatsApp phone_number_id)

        Returns:
            InboxCredentials with access_token and optional platform_account_id

        Raises:
            InboxNotFoundError: If inbox_id is not recognized
        """
        ...

    @abstractmethod
    async def validate_inbox(self, inbox_id: str) -> bool:
        """
        Check if an inbox exists and is active.

        Args:
            inbox_id: The inbox identifier to validate

        Returns:
            True if inbox is valid and active
        """
        ...
