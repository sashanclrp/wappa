"""Backward-compatible imports for recipient normalization utilities."""

from wappa.schemas.core.recipient import (
    BSUID_PATTERN,
    ISO_ALPHA2_CODES,
    PHONE_PATTERN,
    PHONE_SANITIZE_PATTERN,
    RecipientIdentifier,
    RecipientKind,
    ResolvedRecipient,
    apply_recipient_to_payload,
    looks_like_bsuid,
    looks_like_phone_number,
    normalize_recipient_identifier,
    resolve_recipient,
)

__all__ = [
    "BSUID_PATTERN",
    "ISO_ALPHA2_CODES",
    "PHONE_PATTERN",
    "PHONE_SANITIZE_PATTERN",
    "RecipientIdentifier",
    "RecipientKind",
    "ResolvedRecipient",
    "apply_recipient_to_payload",
    "looks_like_bsuid",
    "looks_like_phone_number",
    "normalize_recipient_identifier",
    "resolve_recipient",
]
