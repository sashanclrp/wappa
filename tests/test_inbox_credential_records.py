"""Canonical Inbox Credential Records and index records (PRD 2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from wappa.core.security import CredentialCodec, SecretBinding
from wappa.domain.inbox import (
    EncryptedSecretEnvelope,
    InboxCredentialService,
    InboxCredentialStatus,
    InboxRef,
    PlatformAccountActiveIndexRecord,
    PlatformAccountEmptyIndexRecord,
    PlatformAccountRef,
    WhatsAppActiveInboxCredentialRecord,
    WhatsAppInactiveInboxCredentialRecord,
    dump_record_for_storage,
    parse_inbox_credential_record,
)
from wappa.domain.inbox.credentials import parse_platform_account_index_record
from wappa.schemas.core.types import PlatformType

KEY = CredentialCodec.generate_key()
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _envelope(inbox_id: str = "111") -> EncryptedSecretEnvelope:
    return CredentialCodec(KEY).encrypt(
        SecretStr("token"),
        binding=SecretBinding(PlatformType.WHATSAPP, inbox_id, "access_token"),
    )


def _active(**overrides: object) -> WhatsAppActiveInboxCredentialRecord:
    data: dict[str, object] = {
        "inbox_id": "111",
        "platform_account_id": "9001",
        "credential_version": 1,
        "updated_at": NOW,
        "access_token": _envelope(),
    }
    data.update(overrides)
    return WhatsAppActiveInboxCredentialRecord(**data)  # type: ignore[arg-type]


def test_active_record_serializes_both_discriminators() -> None:
    record = _active()

    stored = dump_record_for_storage(record)

    assert stored["platform"] == "whatsapp"
    assert stored["status"] == "active"
    assert stored["schema_version"] == 1
    assert (
        stored["access_token"]["ciphertext"]
        == record.access_token.ciphertext.get_secret_value()
    )
    assert parse_inbox_credential_record(stored) == record
    assert record.inbox_ref == InboxRef.whatsapp("111")
    assert record.account_ref == PlatformAccountRef.whatsapp("9001")


def test_plain_dump_masks_the_ciphertext() -> None:
    record = _active()

    assert record.model_dump(mode="json")["access_token"]["ciphertext"] == "**********"
    assert record.access_token.ciphertext.get_secret_value() not in repr(record)


def test_inactive_record_cannot_carry_a_token() -> None:
    inactive = WhatsAppInactiveInboxCredentialRecord(
        inbox_id="111", platform_account_id="9001", credential_version=2, updated_at=NOW
    )
    assert inactive.status is InboxCredentialStatus.INACTIVE
    assert inactive.is_active is False

    with pytest.raises(ValidationError):
        WhatsAppInactiveInboxCredentialRecord(
            inbox_id="111",
            platform_account_id="9001",
            credential_version=2,
            updated_at=NOW,
            access_token=_envelope(),  # type: ignore[call-arg]
        )


def test_status_union_rejects_an_active_shape_labelled_inactive() -> None:
    stored = dump_record_for_storage(_active())

    with pytest.raises(ValidationError):
        parse_inbox_credential_record({**stored, "status": "inactive"})
    with pytest.raises(ValidationError):
        parse_inbox_credential_record({**stored, "platform": "telegram"})
    with pytest.raises(ValidationError):
        parse_inbox_credential_record(
            {k: v for k, v in stored.items() if k != "status"}
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"credential_version": 0},
        {"credential_version": -1},
        {"updated_at": datetime(2026, 1, 1)},
        {"inbox_id": ""},
        {"inbox_id": "a:b"},
        {"platform_account_id": " "},
    ],
)
def test_records_require_positive_versions_aware_timestamps_and_strict_ids(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _active(**overrides)


def test_records_are_frozen_and_forbid_extra_fields() -> None:
    record = _active()
    with pytest.raises(ValidationError):
        record.credential_version = 5  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _active(owner_id="x")


def test_credential_service_creates_rotates_and_deactivates() -> None:
    service = InboxCredentialService(CredentialCodec(KEY))

    created = service.create_active_record(
        inbox_ref=InboxRef.whatsapp("111"),
        account_ref=PlatformAccountRef.whatsapp("9001"),
        access_token=SecretStr("first"),
    )
    rotated = service.rotate_active_record(created, access_token=SecretStr("second"))
    inactive = service.create_inactive_record(rotated)

    assert created.credential_version == 1
    assert rotated.credential_version == 2
    assert inactive.credential_version == 3
    assert rotated.access_token != created.access_token
    assert inactive.inbox_ref == created.inbox_ref
    codec = CredentialCodec(KEY)
    binding = SecretBinding(PlatformType.WHATSAPP, "111", "access_token")
    assert (
        codec.decrypt(rotated.access_token, binding=binding).value.get_secret_value()
        == "second"
    )


def test_rotate_encrypted_record_keeps_fields_and_changes_only_the_envelope() -> None:
    old_record = InboxCredentialService(CredentialCodec(KEY)).create_active_record(
        inbox_ref=InboxRef.whatsapp("111"),
        account_ref=PlatformAccountRef.whatsapp("9001"),
        access_token=SecretStr("token"),
    )
    new_key = CredentialCodec.generate_key()
    service = InboxCredentialService(CredentialCodec(new_key, previous_keys=[KEY]))

    rotated = service.rotate_encrypted_record(old_record)

    assert rotated.credential_version == old_record.credential_version
    assert rotated.inbox_ref == old_record.inbox_ref
    assert rotated.updated_at == old_record.updated_at
    assert rotated.access_token != old_record.access_token
    only_new = CredentialCodec(new_key)
    assert (
        only_new.decrypt(
            rotated.access_token,  # type: ignore[union-attr]
            binding=SecretBinding(PlatformType.WHATSAPP, "111", "access_token"),
        ).value.get_secret_value()
        == "token"
    )
    inactive = service.create_inactive_record(old_record)
    assert service.rotate_encrypted_record(inactive) is inactive


def test_credential_service_rejects_cross_platform_inputs() -> None:
    service = InboxCredentialService(CredentialCodec(KEY))
    with pytest.raises(ValueError):
        service.create_active_record(
            inbox_ref=InboxRef(platform=PlatformType.TELEGRAM, inbox_id="1"),
            account_ref=PlatformAccountRef(
                platform=PlatformType.TELEGRAM, platform_account_id="2"
            ),
            access_token=SecretStr("t"),
        )


def test_active_index_record_sorts_and_deduplicates_members() -> None:
    index = PlatformAccountActiveIndexRecord(
        account_ref=PlatformAccountRef.whatsapp("9001"),
        inbox_refs=(
            InboxRef.whatsapp("2"),
            InboxRef.whatsapp("1"),
            InboxRef.whatsapp("2"),
        ),
        index_version=1,
        refreshed_at=NOW,
    )

    assert index.inbox_refs == (InboxRef.whatsapp("1"), InboxRef.whatsapp("2"))
    assert parse_platform_account_index_record(index.model_dump(mode="json")) == index


def test_active_index_record_rejects_empty_or_foreign_members() -> None:
    with pytest.raises(ValidationError):
        PlatformAccountActiveIndexRecord(
            account_ref=PlatformAccountRef.whatsapp("9001"),
            inbox_refs=(),
            index_version=1,
            refreshed_at=NOW,
        )
    with pytest.raises(ValidationError):
        PlatformAccountActiveIndexRecord(
            account_ref=PlatformAccountRef.whatsapp("9001"),
            inbox_refs=(InboxRef(platform=PlatformType.TELEGRAM, inbox_id="1"),),
            index_version=1,
            refreshed_at=NOW,
        )


def test_empty_index_record_round_trips() -> None:
    empty = PlatformAccountEmptyIndexRecord(
        account_ref=PlatformAccountRef.whatsapp("9001"), index_version=3, checked_at=NOW
    )
    assert parse_platform_account_index_record(empty.model_dump(mode="json")) == empty
