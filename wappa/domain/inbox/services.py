"""Inbox Directory orchestration and Wappa-owned credential commands.

``InboxCredentialService`` is what a Host calls before persisting an active
or rotated credential: it validates the fields, encrypts the plaintext, and
returns the canonical record. The Host stores that record and never sees the
envelope's contents again.

``InboxDirectory`` is Wappa's explicit-mode credential authority. It owns
read-through loading, version rules, negative records, Platform Account
index projection and repair, decryption, and Messenger eviction. It is not a
Host extension point; Hosts adapt their durable schema through
``IInboxDirectorySource`` only.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr, ValidationError

from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import PlatformType

from .credentials import (
    PlatformAccountActiveIndexRecord,
    PlatformAccountEmptyIndexRecord,
    SecretBinding,
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
    parse_inbox_credential_record,
    utc_now,
)
from .errors import (
    InboxCredentialIntegrityError,
    InboxDirectoryError,
    InboxDirectoryUnavailableError,
    InboxMutationConflictError,
    InboxNotFoundError,
)
from .identity import InboxRef, PlatformAccountRef
from .ports import (
    CredentialRecord,
    EvictionListener,
    IInboxCredentialResolver,
    IInboxDirectorySource,
    ResolvedInboxCredentials,
)

if TYPE_CHECKING:
    from wappa.core.security.credential_codec import CredentialCodec
    from wappa.persistence.inbox_directory import InboxDirectoryRow, InboxDirectoryTable

WHATSAPP_ACCESS_TOKEN_FIELD = "access_token"


def _binding(inbox_ref: InboxRef) -> SecretBinding:
    return SecretBinding(
        platform=inbox_ref.platform,
        inbox_id=inbox_ref.inbox_id,
        credential_field_name=WHATSAPP_ACCESS_TOKEN_FIELD,
    )


class InboxCredentialService:
    """Create, rotate, and re-encrypt canonical WhatsApp credential records."""

    def __init__(self, codec: CredentialCodec) -> None:
        self._codec = codec

    def create_active_record(
        self,
        *,
        inbox_ref: InboxRef,
        account_ref: PlatformAccountRef,
        access_token: SecretStr,
        credential_version: int = 1,
    ) -> WhatsAppActiveInboxCredentialRecord:
        """Encrypt a plaintext token into a persistable active record."""
        self._require_whatsapp(inbox_ref, account_ref)
        envelope = self._codec.encrypt(access_token, binding=_binding(inbox_ref))
        return WhatsAppActiveInboxCredentialRecord(
            inbox_id=inbox_ref.inbox_id,
            platform_account_id=account_ref.platform_account_id,
            credential_version=credential_version,
            updated_at=utc_now(),
            access_token=envelope,
        )

    def rotate_active_record(
        self,
        previous: CredentialRecord,
        *,
        access_token: SecretStr,
        account_ref: PlatformAccountRef | None = None,
    ) -> WhatsAppActiveInboxCredentialRecord:
        """Produce the next active record with a strictly higher version."""
        target_account = account_ref or previous.account_ref
        return self.create_active_record(
            inbox_ref=previous.inbox_ref,
            account_ref=target_account,
            access_token=access_token,
            credential_version=previous.credential_version + 1,
        )

    def create_inactive_record(
        self, previous: CredentialRecord
    ) -> WhatsAppInactiveInboxCredentialRecord:
        """Produce the deactivation record that follows ``previous``."""
        return WhatsAppInactiveInboxCredentialRecord(
            inbox_id=previous.inbox_id,
            platform_account_id=previous.platform_account_id,
            credential_version=previous.credential_version + 1,
            updated_at=utc_now(),
        )

    def rotate_encrypted_record(self, record: CredentialRecord) -> CredentialRecord:
        """Re-encrypt a record under the active key without exposing plaintext.

        The canonical fields, including ``credential_version``, are unchanged;
        only the envelope is rewritten. Inactive records are returned as-is.
        """
        if not isinstance(record, WhatsAppActiveInboxCredentialRecord):
            return record
        envelope = self._codec.rotate(
            record.access_token, binding=_binding(record.inbox_ref)
        )
        return record.model_copy(update={"access_token": envelope})

    @staticmethod
    def _require_whatsapp(inbox_ref: InboxRef, account_ref: PlatformAccountRef) -> None:
        if inbox_ref.platform is not PlatformType.WHATSAPP:
            raise ValueError("v0.27 ships credential records for WhatsApp only")
        if account_ref.platform is not inbox_ref.platform:
            raise ValueError("Inbox and Platform Account must share a Platform")


class InboxDirectory(IInboxCredentialResolver):
    """Explicit-mode credential authority: read-through directory over a Host source."""

    def __init__(
        self,
        *,
        source: IInboxDirectorySource,
        table: InboxDirectoryTable,
        codec: CredentialCodec,
    ) -> None:
        self._source = source
        self._table = table
        self._codec = codec
        self._listeners: list[EvictionListener] = []
        self.logger = get_logger(__name__)

    # ── eviction ──────────────────────────────────────────────────────

    def subscribe_evictions(self, listener: EvictionListener) -> None:
        self._listeners.append(listener)

    async def _evict(self, inbox_ref: InboxRef) -> None:
        for listener in list(self._listeners):
            outcome = listener(inbox_ref)
            if inspect.isawaitable(outcome):
                await outcome

    async def check_health(self) -> bool:
        """Whether the directory's Table Cache answers a probe read."""
        try:
            await self._table.get_row(InboxRef.whatsapp("0"))
        except InboxDirectoryUnavailableError:
            return False
        return True

    # ── resolver reads ────────────────────────────────────────────────

    async def resolve_credentials(
        self, inbox_ref: InboxRef
    ) -> ResolvedInboxCredentials:
        row = await self._table.get_row(inbox_ref)
        if row is None:
            row = await self._load_from_source(inbox_ref)
        if row.status != "active":
            raise InboxNotFoundError(
                inbox_ref,
                reason="inactive" if row.status == "inactive" else "unknown",
            )
        record = row.credential_record()
        if not isinstance(record, WhatsAppActiveInboxCredentialRecord):
            raise InboxCredentialIntegrityError(
                f"active directory row for {inbox_ref} holds a non-active record"
            )
        credentials = await self._decrypt(row, record)
        await self._table.renew_active(inbox_ref)
        return credentials

    async def get_record(self, inbox_ref: InboxRef) -> CredentialRecord:
        """Return the cached-or-loaded canonical record, active or inactive."""
        row = await self._table.get_row(inbox_ref)
        if row is None:
            row = await self._load_from_source(inbox_ref)
        if row.status == "absent":
            raise InboxNotFoundError(inbox_ref, reason="unknown")
        if row.status == "active":
            await self._table.renew_active(inbox_ref)
        return row.credential_record()

    async def list_inbox_refs_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        index = await self._table.get_index(account_ref)
        if index is None:
            return await self._rebuild_index(account_ref)
        if isinstance(index, PlatformAccountEmptyIndexRecord):
            return ()
        if await self._members_are_valid(index, account_ref):
            await self._table.renew_active_index(account_ref)
            return index.inbox_refs
        self.logger.warning(
            "Platform Account index for %s is stale; repairing from source",
            account_ref,
        )
        return await self._rebuild_index(account_ref)

    # ── commands ──────────────────────────────────────────────────────

    async def refresh_inbox(self, inbox_ref: InboxRef) -> CredentialRecord | None:
        """Reload one Inbox from the source and project it into the directory.

        Returns the canonical record, or ``None`` when the source confirms the
        Inbox is absent (the directory then holds an absent marker). Raises on
        any source, cache, validation, or version failure so the Host can retry.
        """
        previous = await self._table.get_row(inbox_ref)
        previous_account = self._account_of(previous)
        record = await self._source_get(inbox_ref)
        if record is None:
            await self._table.put_absent(inbox_ref, replace_existing=True)
            if previous_account is not None:
                await self._table.adjust_index_membership(
                    previous_account, remove=inbox_ref
                )
            await self._evict(inbox_ref)
            return None

        await self._table.put_record(record)
        if previous_account is not None and previous_account != record.account_ref:
            await self._table.adjust_index_membership(
                previous_account, remove=inbox_ref
            )
        if record.is_active:
            await self._table.adjust_index_membership(record.account_ref, add=inbox_ref)
        else:
            await self._table.adjust_index_membership(
                record.account_ref, remove=inbox_ref
            )
        await self._evict(inbox_ref)
        return record

    async def deactivate_inbox(
        self, inbox_ref: InboxRef
    ) -> WhatsAppInactiveInboxCredentialRecord:
        """Refresh after the Host committed an inactive state.

        Raises ``InboxMutationConflictError`` when the source still reports
        the Inbox active, and ``InboxNotFoundError`` when it is absent.
        """
        record = await self.refresh_inbox(inbox_ref)
        if record is None:
            raise InboxNotFoundError(inbox_ref, reason="absent at the source")
        if not isinstance(record, WhatsAppInactiveInboxCredentialRecord):
            raise InboxMutationConflictError(
                f"source still reports {inbox_ref} as active; commit the inactive "
                "state before calling deactivate_inbox"
            )
        return record

    # ── internals ─────────────────────────────────────────────────────

    async def _source_get(self, inbox_ref: InboxRef) -> CredentialRecord | None:
        try:
            raw = await self._source.get_inbox(inbox_ref)
        except InboxDirectoryError:
            raise
        except Exception as exc:
            raise InboxDirectoryUnavailableError(
                f"Inbox Directory source failed for {inbox_ref}: {type(exc).__name__}"
            ) from exc
        if raw is None:
            return None
        record = self._validate_record(raw)
        if record.inbox_ref != inbox_ref:
            raise InboxCredentialIntegrityError(
                f"source returned a record for {record.inbox_ref} when asked for {inbox_ref}"
            )
        return record

    async def _source_list(
        self, account_ref: PlatformAccountRef
    ) -> tuple[CredentialRecord, ...]:
        try:
            raw_records = await self._source.list_inboxes_for_platform_account(
                account_ref
            )
        except InboxDirectoryError:
            raise
        except Exception as exc:
            raise InboxDirectoryUnavailableError(
                f"Inbox Directory source failed for {account_ref}: {type(exc).__name__}"
            ) from exc
        records: list[CredentialRecord] = []
        for raw in raw_records:
            record = self._validate_record(raw)
            if record.account_ref != account_ref:
                raise InboxCredentialIntegrityError(
                    f"source listed {record.inbox_ref} under {account_ref} but the "
                    f"record names {record.account_ref}"
                )
            records.append(record)
        return tuple(records)

    @staticmethod
    def _validate_record(raw: Any) -> CredentialRecord:
        try:
            return parse_inbox_credential_record(raw)
        except ValidationError as exc:
            raise InboxCredentialIntegrityError(
                "source returned a record that is not a canonical Inbox Credential Record"
            ) from exc

    async def _load_from_source(self, inbox_ref: InboxRef) -> InboxDirectoryRow:
        record = await self._source_get(inbox_ref)
        if record is None:
            return await self._table.put_absent(inbox_ref)
        try:
            return await self._table.put_record(record)
        except InboxMutationConflictError:
            # A concurrent writer stored a newer row; serve what the directory holds.
            current = await self._table.get_row(inbox_ref)
            if current is None:
                raise
            return current

    async def _decrypt(
        self,
        row: InboxDirectoryRow,
        record: WhatsAppActiveInboxCredentialRecord,
    ) -> ResolvedInboxCredentials:
        inbox_ref = record.inbox_ref
        decrypted = self._codec.decrypt(
            record.access_token, binding=_binding(inbox_ref)
        )
        if not decrypted.encrypted_with_active_key:
            rotated = self._codec.encrypt(decrypted.value, binding=_binding(inbox_ref))
            rewritten = record.model_copy(update={"access_token": rotated})
            try:
                await self._table.rewrite_record(row, rewritten)
            except InboxDirectoryUnavailableError:
                self.logger.warning(
                    "Could not rewrite the cached envelope for %s under the active key",
                    inbox_ref,
                )
        return ResolvedInboxCredentials(
            inbox_ref=inbox_ref,
            account_ref=record.account_ref,
            access_token=decrypted.value,
            credential_version=record.credential_version,
        )

    async def _members_are_valid(
        self, index: PlatformAccountActiveIndexRecord, account_ref: PlatformAccountRef
    ) -> bool:
        for member in index.inbox_refs:
            row = await self._table.get_row(member)
            if row is None or row.status != "active":
                return False
            record = row.credential_record()
            if record.inbox_ref != member or record.account_ref != account_ref:
                return False
            await self._table.renew_active(member)
        return True

    async def _rebuild_index(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxRef, ...]:
        records = await self._source_list(account_ref)
        for record in records:
            try:
                await self._table.put_record(record)
            except InboxMutationConflictError as exc:
                raise InboxDirectoryUnavailableError(
                    f"Platform Account index repair for {account_ref} hit a version "
                    f"conflict: {exc}"
                ) from exc
        members = tuple(sorted({r.inbox_ref for r in records if r.is_active}))
        await self._table.put_index_members(account_ref, members)
        return members

    @staticmethod
    def _account_of(row: InboxDirectoryRow | None) -> PlatformAccountRef | None:
        if row is None or row.status == "absent" or row.record is None:
            return None
        try:
            return row.credential_record().account_ref
        except InboxCredentialIntegrityError:
            return None


__all__ = [
    "WHATSAPP_ACCESS_TOKEN_FIELD",
    "InboxCredentialService",
    "InboxDirectory",
]
