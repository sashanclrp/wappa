"""
Core recipient normalization and transport routing utilities.

This module keeps Wappa's framework-facing `recipient` contract stable while
resolving identifiers into the appropriate transport fields for providers that
distinguish between phone numbers and business-scoped user identifiers.

Current transport mapping targets WhatsApp Cloud API:
- `to` for phone numbers
- `recipient` for BSUIDs
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from ._iso_countries import ISO_ALPHA2_CODES


class RecipientKind(StrEnum):
    """Supported outbound recipient identifier kinds."""

    PHONE_NUMBER = "phone_number"
    BSUID = "bsuid"


BSUID_PATTERN = re.compile(
    r"^(?P<country_code>[A-Z]{2})\.(?:(?P<enterprise>ENT)\.)?"
    r"(?P<body>[A-Za-z0-9]{1,128})$",
    re.IGNORECASE,
)
PHONE_SANITIZE_PATTERN = re.compile(r"[\s\-\(\)]")
PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,20}$")

# ``MessageResult.error_code`` when a Platform cannot send this message type to
# a BSUID address; the HTTP layer answers it with 400.
BSUID_ERROR_TAG = "BSUID_RECIPIENT_NOT_SUPPORTED"


def _normalize_bsuid(value: str) -> str:
    """Normalize the country and optional enterprise marker."""
    normalized = value.strip()
    if len(normalized) >= 2:
        normalized = normalized[:2].upper() + normalized[2:]
    if normalized[2:7].lower() == ".ent.":
        normalized = normalized[:3] + "ENT" + normalized[6:]
    return normalized


class ResolvedRecipient(BaseModel):
    """Normalized recipient resolved for outbound transport."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    original: str = Field(..., min_length=1)
    kind: RecipientKind
    phone_number: str | None = None
    bsuid: str | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        """Normalize phone numbers to a compact representation."""
        if value is None:
            return value

        normalized = PHONE_SANITIZE_PATTERN.sub("", value.strip())
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError(f"Invalid WhatsApp phone number format: {value}")
        return normalized

    @field_validator("bsuid")
    @classmethod
    def validate_bsuid(cls, value: str | None) -> str | None:
        """Validate BSUID format including ISO alpha-2 country prefix."""
        if value is None:
            return value

        normalized = _normalize_bsuid(value)
        match = BSUID_PATTERN.fullmatch(normalized)
        if match is None:
            raise ValueError(f"Invalid BSUID format: {value}")
        if match.group("country_code").upper() not in ISO_ALPHA2_CODES:
            raise ValueError(f"Unsupported BSUID country prefix: {value}")
        return normalized

    @property
    def transport_field(self) -> str:
        """Return the platform request field that should carry this identifier."""
        return "recipient" if self.kind == RecipientKind.BSUID else "to"

    @property
    def transport_value(self) -> str:
        """Return the normalized identifier for the selected transport field."""
        if self.kind == RecipientKind.BSUID:
            if self.bsuid is None:
                raise ValueError("BSUID recipient is missing bsuid value")
            return self.bsuid
        if self.phone_number is None:
            raise ValueError("Phone recipient is missing phone number value")
        return self.phone_number

    def apply_to_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply normalized recipient routing to an outbound payload."""
        resolved_payload = dict(payload)
        resolved_payload.pop("to", None)
        resolved_payload.pop("recipient", None)
        resolved_payload[self.transport_field] = self.transport_value
        return resolved_payload


def looks_like_bsuid(value: str) -> bool:
    """Return True when the identifier matches the BSUID public shape."""
    normalized = _normalize_bsuid(value)
    match = BSUID_PATTERN.fullmatch(normalized)
    return bool(match and match.group("country_code").upper() in ISO_ALPHA2_CODES)


def looks_like_phone_number(value: str) -> bool:
    """Return True when the identifier matches the phone transport shape."""
    normalized = PHONE_SANITIZE_PATTERN.sub("", value.strip())
    return bool(PHONE_PATTERN.fullmatch(normalized))


def resolve_recipient(value: str) -> ResolvedRecipient:
    """Resolve a framework-level recipient string into a transport target."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("Recipient identifier cannot be empty")

    if looks_like_bsuid(normalized):
        return ResolvedRecipient(
            original=normalized,
            kind=RecipientKind.BSUID,
            bsuid=normalized,
        )

    if looks_like_phone_number(normalized):
        return ResolvedRecipient(
            original=normalized,
            kind=RecipientKind.PHONE_NUMBER,
            phone_number=normalized,
        )

    raise ValueError(
        "Recipient identifier must be a WhatsApp phone number or a BSUID like "
        "'CO.123ABC'"
    )


def is_bsuid_digit_echo(phone: str, *identifiers: str | None) -> bool:
    """Exclude only a numeric suffix corroborated by a valid BSUID."""
    normalized = PHONE_SANITIZE_PATTERN.sub("", phone.strip()).removeprefix("+")
    return any(
        identifier
        and looks_like_bsuid(identifier)
        and (suffix := identifier.strip().rsplit(".", 1)[-1]).isascii()
        and suffix.isdigit()
        and normalized == suffix
        for identifier in identifiers
    )


def whatsapp_delivery_order(
    addresses: tuple[str, ...],
    *,
    phone_only: bool = False,
    evidence: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Order a User's WhatsApp Delivery Addresses: phones first, then BSUIDs.

    Meta: "If the user's phone number is not present (the wa_id property is
    missing), you can use their BSUID", and ``to`` (phone) wins when both are
    sent. Authentication Templates need a phone (``phone_only``). Unrecognised
    values keep their place after both so the Platform reports them.
    """
    identifiers = (*addresses, *evidence)
    phones: list[str] = []
    seen: set[str] = set()
    for a in addresses:
        if looks_like_phone_number(a) and not is_bsuid_digit_echo(a, *identifiers):
            key = "".join(ch for ch in a if ch.isdigit())
            if key not in seen:  # "573…" and "+57 3…" are one phone
                seen.add(key)
                phones.append(normalize_recipient_identifier(a))
    bsuids = tuple(
        normalize_recipient_identifier(a) for a in addresses if looks_like_bsuid(a)
    )
    if phone_only:
        return tuple(phones)
    others = tuple(
        a for a in addresses if not looks_like_phone_number(a) and a not in bsuids
    )
    return tuple(phones) + bsuids + others


def normalize_recipient_identifier(value: str) -> str:
    """Return the canonical recipient identifier representation used by Wappa."""
    resolved = resolve_recipient(value)
    return resolved.transport_value


def apply_recipient_to_payload(
    payload: dict[str, Any], recipient: str
) -> ResolvedRecipient:
    """Resolve recipient and return the normalized target after mutating payload."""
    resolved = resolve_recipient(recipient)
    updated_payload = resolved.apply_to_payload(payload)
    payload.clear()
    payload.update(updated_payload)
    return resolved


RecipientIdentifier = Annotated[str, AfterValidator(normalize_recipient_identifier)]


def opaque_address(value: str) -> str:
    """Preserve address content; only the selected adapter interprets it."""
    if not value.strip():
        raise ValueError("Delivery Address must not be blank")
    return value


OpaqueAddress = Annotated[str, AfterValidator(opaque_address)]


class RecipientRequest(BaseModel):
    """Shared request boundary for models that accept a recipient identifier."""

    recipient: OpaqueAddress = Field(
        ..., min_length=1, description="Opaque Platform Delivery Address"
    )
    user_id: str | None = Field(
        default=None,
        description=(
            "Canonical domain identifier for the user. Opaque to Wappa — used "
            "as the key for state/cache lookups inside event handlers. Defaults "
            "to `recipient` when omitted."
        ),
    )


class DeliveryRequest(RecipientRequest):
    """A send request: ``recipient`` plus the User's other known addresses."""

    addresses: list[OpaqueAddress] = Field(
        default_factory=list,
        description=(
            "Other addresses of the same User, tried after `recipient` when the "
            "Platform rejects the address itself (WhatsApp: pass the BSUID and "
            "the phone; ADR-0022). Ignored where a User has one address"
        ),
    )


__all__ = [
    "whatsapp_delivery_order",
    "BSUID_ERROR_TAG",
    "BSUID_PATTERN",
    "ISO_ALPHA2_CODES",
    "PHONE_PATTERN",
    "PHONE_SANITIZE_PATTERN",
    "RecipientIdentifier",
    "RecipientRequest",
    "DeliveryRequest",
    "RecipientKind",
    "ResolvedRecipient",
    "apply_recipient_to_payload",
    "looks_like_bsuid",
    "looks_like_phone_number",
    "normalize_recipient_identifier",
    "resolve_recipient",
]
