"""Fernet-based, context-bound encryption for Inbox credential secrets.

Wappa encrypts a small JSON document rather than the bare token. The document
binds the envelope to its format version, Platform, ``inbox_id``, and the
credential field it protects, so a ciphertext copied into another Inbox's
record fails validation even though both use the same key.

Keys follow ``MultiFernet`` semantics: new writes use the active key, reads
try the active key first and then the ordered previous keys. A read that only
succeeds under a previous key reports that, so the caller can rewrite the
value under the active key.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from wappa.domain.inbox.credentials import EncryptedSecretEnvelope, SecretBinding
from wappa.domain.inbox.errors import InboxCredentialIntegrityError

ENVELOPE_FORMAT_VERSION: Final[int] = 1


class CredentialCodecConfigurationError(ValueError):
    """The encryption key configuration is missing or malformed.

    The message never echoes key material.
    """


@dataclass(frozen=True, slots=True)
class DecryptedSecret:
    value: SecretStr
    encrypted_with_active_key: bool


def _build_fernet(key: str, *, label: str) -> Fernet:
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # ValueError, binascii.Error, TypeError
        raise CredentialCodecConfigurationError(
            f"{label} is not a valid Fernet key (expected a URL-safe base64 "
            "encoded 32-byte key such as Fernet.generate_key())"
        ) from exc


class CredentialCodec:
    """Encrypt, decrypt, and re-encrypt Wappa credential envelopes."""

    def __init__(
        self,
        active_key: SecretStr | str,
        previous_keys: Sequence[SecretStr | str] = (),
    ) -> None:
        active = (
            active_key.get_secret_value()
            if isinstance(active_key, SecretStr)
            else active_key
        )
        if not active or not active.strip():
            raise CredentialCodecConfigurationError(
                "SYSTEM_TOKEN_ENC_KEY is required and must not be blank"
            )
        self._active = _build_fernet(active.strip(), label="SYSTEM_TOKEN_ENC_KEY")
        self._previous: list[Fernet] = []
        for index, key in enumerate(previous_keys, start=1):
            raw = key.get_secret_value() if isinstance(key, SecretStr) else key
            if not raw or not raw.strip():
                raise CredentialCodecConfigurationError(
                    f"SYSTEM_TOKEN_ENC_PREVIOUS_KEYS entry {index} is blank"
                )
            self._previous.append(
                _build_fernet(
                    raw.strip(), label=f"SYSTEM_TOKEN_ENC_PREVIOUS_KEYS entry {index}"
                )
            )

    @classmethod
    def from_environment(
        cls,
        active_key: str | None,
        previous_keys: str | None = None,
    ) -> CredentialCodec:
        """Build from the raw environment values.

        ``previous_keys`` is an ordered, comma-separated key ring.
        """
        previous = (
            [part for part in (p.strip() for p in previous_keys.split(",")) if part]
            if previous_keys
            else []
        )
        return cls(active_key or "", previous)

    @property
    def previous_key_count(self) -> int:
        return len(self._previous)

    @staticmethod
    def generate_key() -> str:
        """Return a fresh Fernet key suitable for ``SYSTEM_TOKEN_ENC_KEY``."""
        return Fernet.generate_key().decode("utf-8")

    # ── operations ──────────────────────────────────────────────────────

    def encrypt(
        self, plaintext: SecretStr, *, binding: SecretBinding
    ) -> EncryptedSecretEnvelope:
        secret = plaintext.get_secret_value()
        if not secret:
            raise ValueError("a credential secret must not be empty")
        document = {
            "format_version": ENVELOPE_FORMAT_VERSION,
            "platform": binding.platform.value,
            "inbox_id": binding.inbox_id,
            "credential_field_name": binding.credential_field_name,
            "secret": secret,
        }
        token = self._active.encrypt(
            json.dumps(document, separators=(",", ":")).encode("utf-8")
        )
        return EncryptedSecretEnvelope(
            format_version=1, ciphertext=SecretStr(token.decode("utf-8"))
        )

    def decrypt(
        self, envelope: EncryptedSecretEnvelope, *, binding: SecretBinding
    ) -> DecryptedSecret:
        if envelope.format_version != ENVELOPE_FORMAT_VERSION:
            raise InboxCredentialIntegrityError(
                "unsupported encrypted envelope format version"
            )
        token = envelope.ciphertext.get_secret_value().encode("utf-8")
        payload, active = self._open(token)
        document = self._parse_document(payload)
        self._check_binding(document, binding)
        return DecryptedSecret(
            value=SecretStr(str(document["secret"])),
            encrypted_with_active_key=active,
        )

    def rotate(
        self, envelope: EncryptedSecretEnvelope, *, binding: SecretBinding
    ) -> EncryptedSecretEnvelope:
        """Return the same secret re-encrypted under the active key."""
        decrypted = self.decrypt(envelope, binding=binding)
        return self.encrypt(decrypted.value, binding=binding)

    # ── internals ───────────────────────────────────────────────────────

    def _open(self, token: bytes) -> tuple[bytes, bool]:
        try:
            return self._active.decrypt(token), True
        except InvalidToken:
            pass
        for fernet in self._previous:
            try:
                return fernet.decrypt(token), False
            except InvalidToken:
                continue
        raise InboxCredentialIntegrityError(
            "encrypted credential could not be opened with any accepted key"
        )

    @staticmethod
    def _parse_document(payload: bytes) -> dict[str, Any]:
        try:
            document = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise InboxCredentialIntegrityError(
                "encrypted credential payload is malformed"
            ) from exc
        if not isinstance(document, dict) or "secret" not in document:
            raise InboxCredentialIntegrityError(
                "encrypted credential payload is malformed"
            )
        return document

    @staticmethod
    def _check_binding(document: dict[str, Any], binding: SecretBinding) -> None:
        expected = {
            "format_version": ENVELOPE_FORMAT_VERSION,
            "platform": binding.platform.value,
            "inbox_id": binding.inbox_id,
            "credential_field_name": binding.credential_field_name,
        }
        for field, value in expected.items():
            if document.get(field) != value:
                raise InboxCredentialIntegrityError(
                    "encrypted credential is bound to a different "
                    f"{field.replace('_', ' ')}"
                )


__all__ = [
    "ENVELOPE_FORMAT_VERSION",
    "CredentialCodec",
    "CredentialCodecConfigurationError",
    "DecryptedSecret",
    "SecretBinding",
]
