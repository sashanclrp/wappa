"""Wappa-owned credential encryption: binding, redaction, and key rotation (PRD 2)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from wappa.core.security import (
    CredentialCodec,
    CredentialCodecConfigurationError,
    SecretBinding,
)
from wappa.domain.inbox import (
    EncryptedSecretEnvelope,
    InboxCredentialIntegrityError,
    InboxRef,
)
from wappa.schemas.core.types import PlatformType

KEY_A = CredentialCodec.generate_key()
KEY_B = CredentialCodec.generate_key()
BINDING = SecretBinding(PlatformType.WHATSAPP, "111", "access_token")
TOKEN = SecretStr("EAAB-plaintext-token")


def test_round_trip_under_the_active_key() -> None:
    codec = CredentialCodec(KEY_A)
    envelope = codec.encrypt(TOKEN, binding=BINDING)

    decrypted = codec.decrypt(envelope, binding=BINDING)

    assert decrypted.value.get_secret_value() == TOKEN.get_secret_value()
    assert decrypted.encrypted_with_active_key is True
    assert envelope.format_version == 1


def test_envelope_never_reveals_ciphertext_or_plaintext_by_default() -> None:
    envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)
    ciphertext = envelope.ciphertext.get_secret_value()

    assert ciphertext not in repr(envelope)
    assert ciphertext not in str(envelope)
    assert envelope.model_dump()["ciphertext"] == "**********"
    assert envelope.model_dump(mode="json")["ciphertext"] == "**********"
    assert TOKEN.get_secret_value() not in ciphertext
    assert envelope.for_storage()["ciphertext"] == ciphertext


def test_a_masked_envelope_cannot_be_reloaded_silently() -> None:
    envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)

    with pytest.raises(ValidationError, match="redaction mask"):
        EncryptedSecretEnvelope.model_validate(envelope.model_dump())


def test_ciphertext_copied_to_another_inbox_fails_integrity() -> None:
    codec = CredentialCodec(KEY_A)
    envelope = codec.encrypt(TOKEN, binding=BINDING)

    other_inbox = SecretBinding(PlatformType.WHATSAPP, "222", "access_token")
    with pytest.raises(InboxCredentialIntegrityError, match="inbox id"):
        codec.decrypt(envelope, binding=other_inbox)


def test_ciphertext_copied_to_another_field_or_platform_fails_integrity() -> None:
    codec = CredentialCodec(KEY_A)
    envelope = codec.encrypt(TOKEN, binding=BINDING)

    with pytest.raises(InboxCredentialIntegrityError, match="credential field name"):
        codec.decrypt(
            envelope, binding=SecretBinding(PlatformType.WHATSAPP, "111", "refresh")
        )
    with pytest.raises(InboxCredentialIntegrityError, match="platform"):
        codec.decrypt(
            envelope,
            binding=SecretBinding(PlatformType.TELEGRAM, "111", "access_token"),
        )


def test_wrong_key_and_corrupt_ciphertext_fail_closed() -> None:
    envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)

    with pytest.raises(InboxCredentialIntegrityError, match="accepted key"):
        CredentialCodec(KEY_B).decrypt(envelope, binding=BINDING)

    corrupt = EncryptedSecretEnvelope(ciphertext=SecretStr("not-a-fernet-token"))
    with pytest.raises(InboxCredentialIntegrityError):
        CredentialCodec(KEY_A).decrypt(corrupt, binding=BINDING)


def test_previous_key_reads_are_accepted_and_reported() -> None:
    old_envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)
    rotated_codec = CredentialCodec(KEY_B, previous_keys=[KEY_A])

    decrypted = rotated_codec.decrypt(old_envelope, binding=BINDING)

    assert decrypted.value.get_secret_value() == TOKEN.get_secret_value()
    assert decrypted.encrypted_with_active_key is False


def test_rotate_re_encrypts_under_the_active_key_without_plaintext() -> None:
    old_envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)
    rotated_codec = CredentialCodec(KEY_B, previous_keys=[KEY_A])

    new_envelope = rotated_codec.rotate(old_envelope, binding=BINDING)

    assert (
        new_envelope.ciphertext.get_secret_value()
        != old_envelope.ciphertext.get_secret_value()
    )
    assert (
        CredentialCodec(KEY_B)
        .decrypt(new_envelope, binding=BINDING)
        .encrypted_with_active_key
    )
    with pytest.raises(InboxCredentialIntegrityError):
        CredentialCodec(KEY_A).decrypt(new_envelope, binding=BINDING)


def test_losing_every_accepted_key_makes_the_secret_unrecoverable() -> None:
    envelope = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)

    with pytest.raises(InboxCredentialIntegrityError):
        CredentialCodec(KEY_B, previous_keys=[CredentialCodec.generate_key()]).decrypt(
            envelope, binding=BINDING
        )


@pytest.mark.parametrize("bad_key", ["", "   ", "not-base64", "c2hvcnQ="])
def test_malformed_active_key_is_a_configuration_error_without_echo(
    bad_key: str,
) -> None:
    with pytest.raises(CredentialCodecConfigurationError) as exc_info:
        CredentialCodec(bad_key)

    assert "SYSTEM_TOKEN_ENC_KEY" in str(exc_info.value)
    if bad_key.strip():
        assert bad_key not in str(exc_info.value)


def test_malformed_previous_key_names_its_position_without_echo() -> None:
    with pytest.raises(
        CredentialCodecConfigurationError, match="PREVIOUS_KEYS entry 2"
    ):
        CredentialCodec(KEY_A, previous_keys=[KEY_B, "garbage"])


def test_from_environment_parses_the_ordered_key_ring() -> None:
    codec = CredentialCodec.from_environment(KEY_B, f" {KEY_A} , ,{KEY_B} ")

    assert codec.previous_key_count == 2
    old = CredentialCodec(KEY_A).encrypt(TOKEN, binding=BINDING)
    assert codec.decrypt(old, binding=BINDING).encrypted_with_active_key is False


def test_missing_active_key_is_rejected() -> None:
    with pytest.raises(CredentialCodecConfigurationError, match="required"):
        CredentialCodec.from_environment(None, None)


def test_empty_secret_cannot_be_encrypted() -> None:
    with pytest.raises(ValueError):
        CredentialCodec(KEY_A).encrypt(SecretStr(""), binding=BINDING)


def test_two_inboxes_may_share_one_physical_token_without_sharing_envelopes() -> None:
    codec = CredentialCodec(KEY_A)
    one = codec.encrypt(TOKEN, binding=BINDING)
    two = codec.encrypt(
        TOKEN, binding=SecretBinding(PlatformType.WHATSAPP, "222", "access_token")
    )

    assert one.ciphertext.get_secret_value() != two.ciphertext.get_secret_value()
    with pytest.raises(InboxCredentialIntegrityError):
        codec.decrypt(
            one, binding=SecretBinding(PlatformType.WHATSAPP, "222", "access_token")
        )
    assert InboxRef.whatsapp("111") != InboxRef.whatsapp("222")
