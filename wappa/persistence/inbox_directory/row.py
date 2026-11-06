"""Inbox Directory row: one stored Inbox record, absent marker or inactive row."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
)

from wappa.domain.inbox.credentials import (
    CredentialRecord,
    dump_record_for_storage,
    parse_inbox_credential_record,
    utc_now,
)
from wappa.domain.inbox.errors import (
    InboxCredentialIntegrityError,
)
from wappa.domain.inbox.identity import InboxRef
from wappa.schemas.core.types import PlatformType

RowStatus = Literal["active", "inactive", "absent"]


class InboxDirectoryRow(BaseModel):
    """One primary directory row. Scalars stay top-level for compare-and-set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    status: RowStatus
    platform: PlatformType
    inbox_id: str
    credential_version: int
    record: dict[str, Any] | None = None
    stored_at: AwareDatetime

    @field_validator("inbox_id", mode="before")
    @classmethod
    def _coerce_numeric_ids(cls, value: object) -> object:
        # An untyped Redis hash read returns a numeric ``phone_number_id`` as an
        # int (ADR-0008); the canonical identifier is always a string.
        return (
            str(value)
            if isinstance(value, int) and not isinstance(value, bool)
            else value
        )

    @property
    def inbox_ref(self) -> InboxRef:
        return InboxRef(platform=self.platform, inbox_id=self.inbox_id)

    @property
    def is_negative(self) -> bool:
        return self.status != "active"

    def credential_record(self) -> CredentialRecord:
        if self.record is None:
            raise InboxCredentialIntegrityError(
                f"directory row for {self.inbox_ref} carries no record"
            )
        try:
            return parse_inbox_credential_record(self.record)
        except ValidationError as exc:
            raise InboxCredentialIntegrityError(
                f"directory row for {self.inbox_ref} holds an invalid record"
            ) from exc

    @classmethod
    def from_record(cls, record: CredentialRecord) -> InboxDirectoryRow:
        return cls(
            status="active" if record.is_active else "inactive",
            platform=record.platform,
            inbox_id=record.inbox_id,
            credential_version=record.credential_version,
            record=dump_record_for_storage(record),
            stored_at=utc_now(),
        )

    @classmethod
    def absent(
        cls, inbox_ref: InboxRef, *, credential_version: int = 0
    ) -> InboxDirectoryRow:
        return cls(
            status="absent",
            platform=inbox_ref.platform,
            inbox_id=inbox_ref.inbox_id,
            credential_version=credential_version,
            record=None,
            stored_at=utc_now(),
        )
