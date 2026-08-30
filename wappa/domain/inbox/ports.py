"""Inbox Directory ports.

``IInboxDirectorySource`` is the one Host Application adaptation point: a
read-only mapping from the Host's durable schema to Wappa's canonical records.

``IInboxCredentialResolver`` is Wappa's internal read capability consumed by
inbound routing, Messenger construction, and HTTP context resolution. Wappa
installs both production implementations itself: the legacy settings adapter
and the Inbox Directory. It is not a Host Application extension point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import SecretStr

from .credentials import (
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
)
from .identity import InboxRef, PlatformAccountRef

CredentialRecord = (
    WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord
)


@runtime_checkable
class IInboxDirectorySource(Protocol):
    """Read-only Host adapter from durable Inbox data to canonical records.

    Both reads use the Host's primary database path by default. A Host that
    serves them from a replica accepts the stale-credential risk itself.
    """

    async def get_inbox(self, inbox_ref: InboxRef) -> CredentialRecord | None:
        """Return the active or inactive record, or ``None`` when never registered."""
        ...

    async def list_inboxes_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[CredentialRecord, ...]:
        """Return every record registered under the Platform Account."""
        ...


@dataclass(frozen=True, slots=True)
class ResolvedInboxCredentials:
    """Short-lived, decrypted credentials for one active Inbox.

    Platform adapters consume this value. It never leaves Wappa.
    """

    inbox_ref: InboxRef
    account_ref: PlatformAccountRef
    access_token: SecretStr
    credential_version: int

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id

    @property
    def platform_account_id(self) -> str:
        return self.account_ref.platform_account_id


EvictionListener = Callable[[InboxRef], Awaitable[None] | None]


class IInboxCredentialResolver(ABC):
    """Wappa's internal read port over one Inbox credential authority."""

    @abstractmethod
    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        """Return decrypted credentials for an active Inbox.

        Raises:
            InboxNotFoundError: the Inbox is confirmed unknown or inactive.
            InboxDirectoryUnavailableError: the answer could not be determined.
            InboxCredentialIntegrityError: the record or envelope is unusable.
        """

    @abstractmethod
    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        """Return the sorted, validated active members of a Platform Account.

        An empty tuple means the account is confirmed to have no active
        Inboxes; unavailability raises ``InboxDirectoryUnavailableError``.
        """

    def subscribe_evictions(self, listener: EvictionListener) -> None:
        """Register a callback invoked after a record refresh or deactivation.

        Resolvers whose records never change may keep this no-op default.
        """
        return None


__all__ = [
    "CredentialRecord",
    "EvictionListener",
    "IInboxCredentialResolver",
    "IInboxDirectorySource",
    "ResolvedInboxCredentials",
]
