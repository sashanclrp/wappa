"""Concrete Inbox Directory storage on ``ITableCache`` under the System Scope.

This module owns table names, primary-key encoding, row serialization, TTL
rules, and the versioned compare-and-set behaviour of directory rows. It knows
nothing about Host sources, encryption keys, or WhatsApp clients: those live
in ``wappa.domain.inbox.services`` and ``wappa.core.security``.

Freshness rules:

| Row                                | TTL           | Read behaviour        |
| ---------------------------------- | ------------- | --------------------- |
| Active Inbox primary row           | 60 min        | renew on every hit    |
| Active Platform Account index      | 60 min        | renew on every hit    |
| Inactive Inbox row                 | fixed 60 min  | never renewed         |
| Confirmed absent Inbox row         | fixed 60 min  | never renewed         |
| Confirmed empty account index      | fixed 60 min  | never renewed         |
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
)

from wappa.domain.inbox.credentials import (
    PlatformAccountActiveIndexRecord,
    PlatformAccountEmptyIndexRecord,
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
    dump_record_for_storage,
    parse_inbox_credential_record,
    parse_platform_account_index_record,
    utc_now,
)
from wappa.domain.inbox.errors import (
    InboxCredentialIntegrityError,
    InboxDirectoryUnavailableError,
    InboxMutationConflictError,
)
from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.interfaces.cache_interfaces import ITableCache, TableRowTransition
from wappa.schemas.core.types import PlatformType

from .scope import SYSTEM_SCOPE

DIRECTORY_TTL_SECONDS: Final[int] = 60 * 60
PRIMARY_TABLE: Final[str] = "wappa_inbox_directory"
ACCOUNT_INDEX_TABLE: Final[str] = "wappa_inbox_directory_account_index"
MAX_MUTATION_ATTEMPTS: Final[int] = 8

CredentialRecord = (
    WhatsAppActiveInboxCredentialRecord | WhatsAppInactiveInboxCredentialRecord
)
IndexRecord = PlatformAccountActiveIndexRecord | PlatformAccountEmptyIndexRecord
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


def _same_canonical_record(left: CredentialRecord, right: CredentialRecord) -> bool:
    """Equal-version writes are idempotent only for an identical canonical record."""
    return dump_record_for_storage(left) == dump_record_for_storage(right)


class InboxDirectoryTable:
    """Wappa-owned directory rows over one System-Scope ``ITableCache``.

    Hosts cannot replace this class, its table names, its TTL rules, or its
    mutation behaviour. The domain service composes it with a source and codec.
    """

    def __init__(self, table: ITableCache) -> None:
        context_id = getattr(table, "context_id", None)
        if context_id != SYSTEM_SCOPE:
            raise ValueError(
                "InboxDirectoryTable requires a Table Cache bound to the System "
                f"Scope {SYSTEM_SCOPE!r}; got {context_id!r}"
            )
        self._table = table

    # ── primary rows ──────────────────────────────────────────────────

    async def get_row(self, inbox_ref: InboxRef) -> InboxDirectoryRow | None:
        raw = await self._guard(
            self._table.get(PRIMARY_TABLE, inbox_ref.cache_namespace),
            "read the Inbox Directory",
        )
        if raw is None:
            return None
        try:
            row = InboxDirectoryRow.model_validate(raw)
        except ValidationError as exc:
            raise InboxCredentialIntegrityError(
                f"directory row for {inbox_ref} is malformed"
            ) from exc
        if row.inbox_ref != inbox_ref:
            raise InboxCredentialIntegrityError(
                f"directory row for {inbox_ref} names a different Inbox"
            )
        return row

    async def renew_active(self, inbox_ref: InboxRef) -> None:
        """Slide the TTL of an active row. Negative rows are never renewed."""
        await self._guard(
            self._table.renew_ttl(
                PRIMARY_TABLE, inbox_ref.cache_namespace, DIRECTORY_TTL_SECONDS
            ),
            "renew an Inbox Directory row",
        )

    async def put_record(self, record: CredentialRecord) -> InboxDirectoryRow:
        """Store a canonical record under the version rules.

        - a higher ``credential_version`` replaces the row;
        - a lower version raises ``InboxMutationConflictError``;
        - an equal version is accepted only for an identical record, in which
          case the row is rewritten (renewing an active TTL) so a retry still
          completes derived work.
        """
        candidate = InboxDirectoryRow.from_record(record)
        pkid = record.inbox_ref.cache_namespace
        for _ in range(MAX_MUTATION_ATTEMPTS):
            current = await self.get_row(record.inbox_ref)
            if current is None:
                result = await self._guard(
                    self._table.create_if_absent(
                        PRIMARY_TABLE, pkid, candidate, ttl=DIRECTORY_TTL_SECONDS
                    ),
                    "write the Inbox Directory",
                )
                if result.transition is TableRowTransition.CREATED:
                    return candidate
                continue

            if record.credential_version < current.credential_version:
                raise InboxMutationConflictError(
                    f"credential_version {record.credential_version} for "
                    f"{record.inbox_ref} is older than the directory's "
                    f"{current.credential_version}"
                )
            if (
                record.credential_version == current.credential_version
                and current.status != "absent"
                and not _same_canonical_record(current.credential_record(), record)
            ):
                raise InboxMutationConflictError(
                    f"credential_version {record.credential_version} for "
                    f"{record.inbox_ref} conflicts with a different stored record"
                )

            result = await self._guard(
                self._table.replace_if(
                    PRIMARY_TABLE,
                    pkid,
                    candidate,
                    expected={
                        "credential_version": current.credential_version,
                        "status": current.status,
                    },
                    ttl=DIRECTORY_TTL_SECONDS,
                ),
                "write the Inbox Directory",
            )
            if result.transition is TableRowTransition.REPLACED:
                return candidate
        raise InboxDirectoryUnavailableError(
            f"could not settle the directory row for {record.inbox_ref} under contention"
        )

    async def put_absent(
        self, inbox_ref: InboxRef, *, replace_existing: bool = False
    ) -> InboxDirectoryRow:
        """Store a fixed-TTL absent marker.

        With ``replace_existing`` (used by refresh commands, where the source is
        authoritative) an existing row is replaced while keeping its version so
        a later recreation must still be strictly newer. Otherwise an existing
        row is left untouched and returned.
        """
        pkid = inbox_ref.cache_namespace
        for _ in range(MAX_MUTATION_ATTEMPTS):
            current = await self.get_row(inbox_ref)
            if current is None:
                candidate = InboxDirectoryRow.absent(inbox_ref)
                result = await self._guard(
                    self._table.create_if_absent(
                        PRIMARY_TABLE, pkid, candidate, ttl=DIRECTORY_TTL_SECONDS
                    ),
                    "write the Inbox Directory",
                )
                if result.transition is TableRowTransition.CREATED:
                    return candidate
                continue
            if not replace_existing or current.status == "absent":
                return current
            candidate = InboxDirectoryRow.absent(
                inbox_ref, credential_version=current.credential_version
            )
            result = await self._guard(
                self._table.replace_if(
                    PRIMARY_TABLE,
                    pkid,
                    candidate,
                    expected={
                        "credential_version": current.credential_version,
                        "status": current.status,
                    },
                    ttl=DIRECTORY_TTL_SECONDS,
                ),
                "write the Inbox Directory",
            )
            if result.transition is TableRowTransition.REPLACED:
                return candidate
        raise InboxDirectoryUnavailableError(
            f"could not settle the absent marker for {inbox_ref} under contention"
        )

    async def rewrite_record(
        self, current: InboxDirectoryRow, record: CredentialRecord
    ) -> bool:
        """Replace a row's stored record in place (same version, e.g. key rotation)."""
        if record.credential_version != current.credential_version:
            raise InboxMutationConflictError("rewrite must keep the credential version")
        candidate = InboxDirectoryRow.from_record(record)
        result = await self._guard(
            self._table.replace_if(
                PRIMARY_TABLE,
                record.inbox_ref.cache_namespace,
                candidate,
                expected={
                    "credential_version": current.credential_version,
                    "status": current.status,
                },
                ttl=DIRECTORY_TTL_SECONDS,
            ),
            "rewrite an Inbox Directory row",
        )
        return result.transition is TableRowTransition.REPLACED

    # ── Platform Account index ────────────────────────────────────────

    async def get_index(self, account_ref: PlatformAccountRef) -> IndexRecord | None:
        raw = await self._guard(
            self._table.get(ACCOUNT_INDEX_TABLE, account_ref.cache_namespace),
            "read the Platform Account index",
        )
        if raw is None:
            return None
        try:
            index = parse_platform_account_index_record(raw)
        except ValidationError as exc:
            raise InboxCredentialIntegrityError(
                f"Platform Account index for {account_ref} is malformed"
            ) from exc
        if index.account_ref != account_ref:
            raise InboxCredentialIntegrityError(
                f"Platform Account index for {account_ref} names a different account"
            )
        return index

    async def renew_active_index(self, account_ref: PlatformAccountRef) -> None:
        await self._guard(
            self._table.renew_ttl(
                ACCOUNT_INDEX_TABLE, account_ref.cache_namespace, DIRECTORY_TTL_SECONDS
            ),
            "renew a Platform Account index",
        )

    async def put_index_members(
        self,
        account_ref: PlatformAccountRef,
        members: tuple[InboxRef, ...],
    ) -> IndexRecord:
        """Replace the index projection with ``members`` using compare-and-set."""
        for _ in range(MAX_MUTATION_ATTEMPTS):
            current = await self.get_index(account_ref)
            next_version = 1 if current is None else current.index_version + 1
            candidate = self._index_record(account_ref, members, next_version)
            pkid = account_ref.cache_namespace
            if current is None:
                result = await self._guard(
                    self._table.create_if_absent(
                        ACCOUNT_INDEX_TABLE, pkid, candidate, ttl=DIRECTORY_TTL_SECONDS
                    ),
                    "write the Platform Account index",
                )
                if result.transition is TableRowTransition.CREATED:
                    return candidate
                continue
            result = await self._guard(
                self._table.replace_if(
                    ACCOUNT_INDEX_TABLE,
                    pkid,
                    candidate,
                    expected={"index_version": current.index_version},
                    ttl=DIRECTORY_TTL_SECONDS,
                ),
                "write the Platform Account index",
            )
            if result.transition is TableRowTransition.REPLACED:
                return candidate
        raise InboxDirectoryUnavailableError(
            f"could not settle the Platform Account index for {account_ref}"
        )

    async def adjust_index_membership(
        self,
        account_ref: PlatformAccountRef,
        *,
        add: InboxRef | None = None,
        remove: InboxRef | None = None,
    ) -> IndexRecord | None:
        """Add or remove one member from an existing index projection.

        An absent index is left absent: a projection built from one record
        would claim completeness it cannot have. The next lookup rebuilds it
        from the source.
        """
        for _ in range(MAX_MUTATION_ATTEMPTS):
            current = await self.get_index(account_ref)
            if current is None:
                return None
            members: set[InboxRef] = (
                set(current.inbox_refs)
                if isinstance(current, PlatformAccountActiveIndexRecord)
                else set()
            )
            if add is not None:
                members.add(add)
            if remove is not None:
                members.discard(remove)
            ordered = tuple(sorted(members))
            candidate = self._index_record(
                account_ref, ordered, current.index_version + 1
            )
            result = await self._guard(
                self._table.replace_if(
                    ACCOUNT_INDEX_TABLE,
                    account_ref.cache_namespace,
                    candidate,
                    expected={"index_version": current.index_version},
                    ttl=DIRECTORY_TTL_SECONDS,
                ),
                "write the Platform Account index",
            )
            if result.transition is TableRowTransition.REPLACED:
                return candidate
            if result.transition is TableRowTransition.MISSING:
                return None
        raise InboxDirectoryUnavailableError(
            f"could not settle the Platform Account index for {account_ref}"
        )

    @staticmethod
    def _index_record(
        account_ref: PlatformAccountRef,
        members: tuple[InboxRef, ...],
        index_version: int,
    ) -> IndexRecord:
        if members:
            return PlatformAccountActiveIndexRecord(
                account_ref=account_ref,
                inbox_refs=members,
                index_version=index_version,
                refreshed_at=utc_now(),
            )
        return PlatformAccountEmptyIndexRecord(
            account_ref=account_ref,
            index_version=index_version,
            checked_at=utc_now(),
        )

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    async def _guard(awaitable: Any, action: str) -> Any:
        """Turn any backend failure into the typed unavailable error."""
        try:
            return await awaitable
        except (
            InboxCredentialIntegrityError,
            InboxMutationConflictError,
            InboxDirectoryUnavailableError,
        ):
            raise
        except Exception as exc:
            raise InboxDirectoryUnavailableError(
                f"Inbox Directory could not {action}: {type(exc).__name__}"
            ) from exc


__all__ = [
    "ACCOUNT_INDEX_TABLE",
    "DIRECTORY_TTL_SECONDS",
    "PRIMARY_TABLE",
    "InboxDirectoryRow",
    "InboxDirectoryTable",
]
