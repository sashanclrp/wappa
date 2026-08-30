"""Canonical Inbox Credential Records and Platform Account index records.

Wappa owns these shapes. A Host Application persists them in any durable
schema it likes and maps its rows back through ``IInboxDirectorySource``, but
it never invents its own record shape, decrypts an envelope, or writes a
directory row.

Two discriminators stay visible in the serialized form: ``platform`` selects
the Platform member and ``status`` selects the active or inactive variant. An
inactive record carries no credential material by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    PositiveInt,
    SecretStr,
    SerializationInfo,
    Tag,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_validator,
)

from wappa.schemas.core.types import PlatformType

from .identity import InboxRef, PlatformAccountRef, validate_platform_native_id

# Serialization context key that lets a storage path read the ciphertext out
# of an envelope. Every other dump masks it, so a record cannot leak its
# ciphertext into logs, events, health data, or exception messages by accident.
SECRET_STORAGE_CONTEXT: Final[dict[str, bool]] = {"wappa_secret_storage": True}
SECRET_MASK: Final[str] = "**********"


class InboxCredentialStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class SecretBinding:
    """The context an Encrypted Secret Envelope is bound to."""

    platform: PlatformType
    inbox_id: str
    credential_field_name: str


class EncryptedSecretEnvelope(BaseModel):
    """Wappa's authenticated, context-bound representation of one secret.

    Hosts persist and return the envelope; only Wappa creates or opens it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal[1] = 1
    ciphertext: SecretStr

    @field_validator("ciphertext", mode="before")
    @classmethod
    def _reject_masked_or_blank(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("ciphertext must be a non-empty string")
        if raw == SECRET_MASK:
            raise ValueError(
                "ciphertext is the redaction mask; persist envelopes through "
                "dump_record_for_storage(), not a plain model_dump()"
            )
        return value

    @field_serializer("ciphertext")
    def _serialize_ciphertext(self, value: SecretStr, info: SerializationInfo) -> str:
        context = info.context
        if isinstance(context, dict) and context.get("wappa_secret_storage"):
            return value.get_secret_value()
        return SECRET_MASK

    def for_storage(self) -> dict[str, Any]:
        """The persistable form: the only dump that carries the ciphertext."""
        return self.model_dump(mode="json", context=SECRET_STORAGE_CONTEXT)


class _InboxCredentialRecordBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    inbox_id: str
    platform_account_id: str
    credential_version: PositiveInt
    updated_at: AwareDatetime

    @field_validator("inbox_id", mode="before")
    @classmethod
    def _validate_inbox_id(cls, value: object) -> str:
        return validate_platform_native_id(value, field_name="inbox_id")

    @field_validator("platform_account_id", mode="before")
    @classmethod
    def _validate_account_id(cls, value: object) -> str:
        return validate_platform_native_id(value, field_name="platform_account_id")

    # Subclasses declare ``platform``; typed here so the properties resolve.
    platform: PlatformType

    @property
    def inbox_ref(self) -> InboxRef:
        return InboxRef(platform=self.platform, inbox_id=self.inbox_id)

    @property
    def account_ref(self) -> PlatformAccountRef:
        return PlatformAccountRef(
            platform=self.platform, platform_account_id=self.platform_account_id
        )

    def for_storage(self) -> dict[str, Any]:
        """The persistable form of the record, ciphertext included."""
        return self.model_dump(mode="json", context=SECRET_STORAGE_CONTEXT)


class WhatsAppActiveInboxCredentialRecord(_InboxCredentialRecordBase):
    """An active WhatsApp Inbox with its encrypted bearer credential."""

    platform: Literal[PlatformType.WHATSAPP] = PlatformType.WHATSAPP
    status: Literal[InboxCredentialStatus.ACTIVE] = InboxCredentialStatus.ACTIVE
    access_token: EncryptedSecretEnvelope

    @property
    def is_active(self) -> Literal[True]:
        return True


class WhatsAppInactiveInboxCredentialRecord(_InboxCredentialRecordBase):
    """A deactivated WhatsApp Inbox. It cannot carry credential material."""

    platform: Literal[PlatformType.WHATSAPP] = PlatformType.WHATSAPP
    status: Literal[InboxCredentialStatus.INACTIVE] = InboxCredentialStatus.INACTIVE

    @property
    def is_active(self) -> Literal[False]:
        return False


def _record_tag(value: Any) -> str | None:
    """Callable discriminator over ``platform`` and ``status`` together."""
    if isinstance(value, dict):
        platform = value.get("platform")
        status = value.get("status")
    else:
        platform = getattr(value, "platform", None)
        status = getattr(value, "status", None)
    if platform is None or status is None:
        return None
    platform_value = platform.value if isinstance(platform, StrEnum) else platform
    status_value = status.value if isinstance(status, StrEnum) else status
    return f"{platform_value}:{status_value}"


InboxCredentialRecord = Annotated[
    Annotated[WhatsAppActiveInboxCredentialRecord, Tag("whatsapp:active")]
    | Annotated[WhatsAppInactiveInboxCredentialRecord, Tag("whatsapp:inactive")],
    Discriminator(_record_tag),
]
"""Platform- and status-discriminated union. v0.27 ships only WhatsApp members."""

WhatsAppInboxCredentialRecord = (
    WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord
)

_record_adapter: TypeAdapter[
    WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord
] = TypeAdapter(InboxCredentialRecord)


def parse_inbox_credential_record(
    data: Any,
) -> WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord:
    """Validate an arbitrary object into the canonical record union."""
    return _record_adapter.validate_python(data)


def dump_record_for_storage(
    record: WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord,
) -> dict[str, Any]:
    """Serialize a record for persistence. This is the only ciphertext-bearing dump."""
    return record.for_storage()


# ── Platform Account reverse index ──────────────────────────────────────────


class PlatformAccountActiveIndexRecord(BaseModel):
    """Cached, sorted, duplicate-free active membership of one Platform Account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal["active"] = "active"
    account_ref: PlatformAccountRef
    inbox_refs: tuple[InboxRef, ...]
    index_version: PositiveInt
    refreshed_at: AwareDatetime

    @model_validator(mode="after")
    def _normalize_members(self) -> PlatformAccountActiveIndexRecord:
        if not self.inbox_refs:
            raise ValueError("an active index must list at least one Inbox")
        ordered = tuple(sorted(set(self.inbox_refs)))
        for ref in ordered:
            if ref.platform is not self.account_ref.platform:
                raise ValueError(
                    f"index member {ref} is not on Platform "
                    f"{self.account_ref.platform.value}"
                )
        if ordered != self.inbox_refs:
            object.__setattr__(self, "inbox_refs", ordered)
        return self


class PlatformAccountEmptyIndexRecord(BaseModel):
    """A confirmed Platform Account with no active Inboxes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal["empty"] = "empty"
    account_ref: PlatformAccountRef
    index_version: PositiveInt
    checked_at: AwareDatetime


PlatformAccountIndexRecord = Annotated[
    PlatformAccountActiveIndexRecord | PlatformAccountEmptyIndexRecord,
    Field(discriminator="status"),
]

_index_adapter: TypeAdapter[
    PlatformAccountActiveIndexRecord | PlatformAccountEmptyIndexRecord
] = TypeAdapter(PlatformAccountIndexRecord)


def parse_platform_account_index_record(
    data: Any,
) -> PlatformAccountActiveIndexRecord | PlatformAccountEmptyIndexRecord:
    return _index_adapter.validate_python(data)


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


__all__ = [
    "SECRET_MASK",
    "SECRET_STORAGE_CONTEXT",
    "EncryptedSecretEnvelope",
    "InboxCredentialRecord",
    "InboxCredentialStatus",
    "PlatformAccountActiveIndexRecord",
    "PlatformAccountEmptyIndexRecord",
    "PlatformAccountIndexRecord",
    "SecretBinding",
    "WhatsAppActiveInboxCredentialRecord",
    "WhatsAppInactiveInboxCredentialRecord",
    "WhatsAppInboxCredentialRecord",
    "dump_record_for_storage",
    "parse_inbox_credential_record",
    "parse_platform_account_index_record",
    "utc_now",
]
