"""Qualified runtime identity for Inboxes and Platform Accounts.

A raw ``inbox_id`` is unique only inside one Platform. Wappa's globally
unique runtime identity is ``InboxRef(platform, inbox_id)``; the same rule
applies to Platform Accounts through ``PlatformAccountRef``. Every module that
persists, caches, routes, or compares these identities across Platforms uses
the qualified value object rather than two loose strings.

Both values expose one Wappa-owned cache namespace encoding. Callers never
rebuild it with ad hoc concatenation.
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, field_validator

from wappa.schemas.core.types import PlatformType

# Version of the namespace encoding. A future delimiter change bumps this so a
# migration can tell old and new key shapes apart instead of guessing.
NAMESPACE_ENCODING_VERSION: Final[int] = 1

# Separator between a Platform and its native identifier in a qualified cache
# namespace. Native identifiers may not contain it, which is what makes a raw
# WhatsApp namespace, a qualified namespace, and the reserved ``__system__``
# scope distinct by construction.
QUALIFIED_NAMESPACE_SEPARATOR: Final[str] = "__"

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._+-]{1,128}$")


def validate_platform_native_id(value: object, *, field_name: str) -> str:
    """Return ``value`` when it is a safe Platform-native identifier.

    The identifier must be a non-blank string that the existing cache key
    scheme can carry unchanged: no key separator (``:``), no SCAN glob syntax,
    no whitespace, and no qualified-namespace separator.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} may contain only letters, digits, '.', '_', '+', '-' "
            "(1-128 characters)"
        )
    if QUALIFIED_NAMESPACE_SEPARATOR in value:
        raise ValueError(
            f"{field_name} must not contain {QUALIFIED_NAMESPACE_SEPARATOR!r}"
        )
    return value


class InboxRef(BaseModel):
    """Wappa's globally unique identity for one Inbox.

    For WhatsApp, ``inbox_id`` is Meta's exact ``phone_number_id``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: PlatformType
    inbox_id: str

    @field_validator("inbox_id", mode="before")
    @classmethod
    def _validate_inbox_id(cls, value: object) -> str:
        return validate_platform_native_id(value, field_name="inbox_id")

    @classmethod
    def whatsapp(cls, phone_number_id: str) -> InboxRef:
        """Build the WhatsApp reference for a Meta ``phone_number_id``."""
        return cls(platform=PlatformType.WHATSAPP, inbox_id=phone_number_id)

    @property
    def cache_namespace(self) -> str:
        """The Wappa-owned first key segment for this Inbox's cache data.

        WhatsApp keeps its raw ``phone_number_id`` so keys written by earlier
        releases stay readable. Every other Platform is qualified.
        """
        if self.platform is PlatformType.WHATSAPP:
            return self.inbox_id
        return f"{self.platform.value}{QUALIFIED_NAMESPACE_SEPARATOR}{self.inbox_id}"

    @property
    def sort_key(self) -> tuple[str, str]:
        """Deterministic ordering: Platform first, then native identifier."""
        return (self.platform.value, self.inbox_id)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, InboxRef):
            return NotImplemented
        return self.sort_key < other.sort_key

    def __str__(self) -> str:
        return f"{self.platform.value}:{self.inbox_id}"

    def __hash__(self) -> int:
        return hash((InboxRef, self.platform, self.inbox_id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, InboxRef):
            return NotImplemented
        return self.platform == other.platform and self.inbox_id == other.inbox_id


class PlatformAccountRef(BaseModel):
    """Wappa's globally unique identity for one Platform Account.

    For WhatsApp, ``platform_account_id`` is the WABA ID (``entry[].id``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: PlatformType
    platform_account_id: str

    @field_validator("platform_account_id", mode="before")
    @classmethod
    def _validate_account_id(cls, value: object) -> str:
        return validate_platform_native_id(value, field_name="platform_account_id")

    @classmethod
    def whatsapp(cls, waba_id: str) -> PlatformAccountRef:
        """Build the WhatsApp reference for a Meta WABA ID."""
        return cls(platform=PlatformType.WHATSAPP, platform_account_id=waba_id)

    @property
    def cache_namespace(self) -> str:
        """Qualified key segment. Account indexes are new, so no raw compatibility."""
        return (
            f"{self.platform.value}{QUALIFIED_NAMESPACE_SEPARATOR}"
            f"{self.platform_account_id}"
        )

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.platform.value, self.platform_account_id)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PlatformAccountRef):
            return NotImplemented
        return self.sort_key < other.sort_key

    def __str__(self) -> str:
        return f"{self.platform.value}:{self.platform_account_id}"

    def __hash__(self) -> int:
        return hash((PlatformAccountRef, self.platform, self.platform_account_id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PlatformAccountRef):
            return NotImplemented
        return (
            self.platform == other.platform
            and self.platform_account_id == other.platform_account_id
        )


__all__ = [
    "NAMESPACE_ENCODING_VERSION",
    "QUALIFIED_NAMESPACE_SEPARATOR",
    "InboxRef",
    "PlatformAccountRef",
    "validate_platform_native_id",
]
