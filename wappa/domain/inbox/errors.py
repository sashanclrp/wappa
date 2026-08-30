"""Typed Inbox Directory failures.

Host code catches these stable categories without importing Redis, Fernet,
HTTP client, or SQL exceptions. Messages may name qualified identity; they
never contain tokens, ciphertext, keys, payloads, or source query details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .identity import InboxRef, PlatformAccountRef


class InboxDirectoryError(Exception):
    """Base class for every Inbox Directory and Inbox credential failure."""


class InboxConfigurationError(InboxDirectoryError):
    """Startup configuration cannot select one Inbox credential authority."""


class InboxNotFoundError(InboxDirectoryError):
    """A healthy lookup confirmed the Inbox is unknown or inactive."""

    def __init__(
        self, inbox_ref: InboxRef, *, reason: str = "unknown or inactive"
    ) -> None:
        self.inbox_ref = inbox_ref
        super().__init__(f"Inbox {inbox_ref} is {reason}")


class InboxMembershipError(InboxDirectoryError):
    """Known identities contradict the required Platform Account relation."""

    def __init__(self, inbox_ref: InboxRef, account_ref: PlatformAccountRef) -> None:
        self.inbox_ref = inbox_ref
        self.account_ref = account_ref
        super().__init__(
            f"Inbox {inbox_ref} does not belong to Platform Account {account_ref}"
        )


class InboxDirectoryUnavailableError(InboxDirectoryError):
    """The directory could not determine an answer: cache, source, or dependency failed."""


class InboxCredentialIntegrityError(InboxDirectoryError):
    """A record or encrypted credential failed validation and cannot be used."""


class InboxMutationConflictError(InboxDirectoryError):
    """A directory mutation lost to a newer or conflicting version."""


__all__ = [
    "InboxConfigurationError",
    "InboxCredentialIntegrityError",
    "InboxDirectoryError",
    "InboxDirectoryUnavailableError",
    "InboxMembershipError",
    "InboxMutationConflictError",
    "InboxNotFoundError",
]
