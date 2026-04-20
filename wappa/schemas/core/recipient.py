"""
Core recipient normalization and transport routing utilities.

This module keeps Wappa's framework-facing `recipient` contract stable while
resolving identifiers into the appropriate transport fields for providers that
distinguish between phone numbers and business-scoped user identifiers.

Current transport mapping targets WhatsApp Cloud API:
- `to` for phone numbers
- `recipient` for BSUIDs
"""

import re
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


class RecipientKind(str, Enum):
    """Supported outbound recipient identifier kinds."""

    PHONE_NUMBER = "phone_number"
    BSUID = "bsuid"


ISO_ALPHA2_CODES = frozenset(
    {
        "AD",
        "AE",
        "AF",
        "AG",
        "AI",
        "AL",
        "AM",
        "AO",
        "AQ",
        "AR",
        "AS",
        "AT",
        "AU",
        "AW",
        "AX",
        "AZ",
        "BA",
        "BB",
        "BD",
        "BE",
        "BF",
        "BG",
        "BH",
        "BI",
        "BJ",
        "BL",
        "BM",
        "BN",
        "BO",
        "BQ",
        "BR",
        "BS",
        "BT",
        "BV",
        "BW",
        "BY",
        "BZ",
        "CA",
        "CC",
        "CD",
        "CF",
        "CG",
        "CH",
        "CI",
        "CK",
        "CL",
        "CM",
        "CN",
        "CO",
        "CR",
        "CU",
        "CV",
        "CW",
        "CX",
        "CY",
        "CZ",
        "DE",
        "DJ",
        "DK",
        "DM",
        "DO",
        "DZ",
        "EC",
        "EE",
        "EG",
        "EH",
        "ER",
        "ES",
        "ET",
        "FI",
        "FJ",
        "FK",
        "FM",
        "FO",
        "FR",
        "GA",
        "GB",
        "GD",
        "GE",
        "GF",
        "GG",
        "GH",
        "GI",
        "GL",
        "GM",
        "GN",
        "GP",
        "GQ",
        "GR",
        "GS",
        "GT",
        "GU",
        "GW",
        "GY",
        "HK",
        "HM",
        "HN",
        "HR",
        "HT",
        "HU",
        "ID",
        "IE",
        "IL",
        "IM",
        "IN",
        "IO",
        "IQ",
        "IR",
        "IS",
        "IT",
        "JE",
        "JM",
        "JO",
        "JP",
        "KE",
        "KG",
        "KH",
        "KI",
        "KM",
        "KN",
        "KP",
        "KR",
        "KW",
        "KY",
        "KZ",
        "LA",
        "LB",
        "LC",
        "LI",
        "LK",
        "LR",
        "LS",
        "LT",
        "LU",
        "LV",
        "LY",
        "MA",
        "MC",
        "MD",
        "ME",
        "MF",
        "MG",
        "MH",
        "MK",
        "ML",
        "MM",
        "MN",
        "MO",
        "MP",
        "MQ",
        "MR",
        "MS",
        "MT",
        "MU",
        "MV",
        "MW",
        "MX",
        "MY",
        "MZ",
        "NA",
        "NC",
        "NE",
        "NF",
        "NG",
        "NI",
        "NL",
        "NO",
        "NP",
        "NR",
        "NU",
        "NZ",
        "OM",
        "PA",
        "PE",
        "PF",
        "PG",
        "PH",
        "PK",
        "PL",
        "PM",
        "PN",
        "PR",
        "PS",
        "PT",
        "PW",
        "PY",
        "QA",
        "RE",
        "RO",
        "RS",
        "RU",
        "RW",
        "SA",
        "SB",
        "SC",
        "SD",
        "SE",
        "SG",
        "SH",
        "SI",
        "SJ",
        "SK",
        "SL",
        "SM",
        "SN",
        "SO",
        "SR",
        "SS",
        "ST",
        "SV",
        "SX",
        "SY",
        "SZ",
        "TC",
        "TD",
        "TF",
        "TG",
        "TH",
        "TJ",
        "TK",
        "TL",
        "TM",
        "TN",
        "TO",
        "TR",
        "TT",
        "TV",
        "TW",
        "TZ",
        "UA",
        "UG",
        "UM",
        "US",
        "UY",
        "UZ",
        "VA",
        "VC",
        "VE",
        "VG",
        "VI",
        "VN",
        "VU",
        "WF",
        "WS",
        "YE",
        "YT",
        "ZA",
        "ZM",
        "ZW",
    }
)

BSUID_PATTERN = re.compile(
    r"^(?P<country_code>[A-Z]{2})\.(?P<body>[A-Za-z0-9]{1,128})$",
    re.IGNORECASE,
)
PHONE_SANITIZE_PATTERN = re.compile(r"[\s\-\(\)]")
PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,20}$")


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

        stripped = value.strip()
        normalized = stripped[:2].upper() + stripped[2:]
        match = BSUID_PATTERN.fullmatch(normalized)
        if match is None:
            raise ValueError(f"Invalid BSUID format: {value}")
        if match.group("country_code").upper() not in ISO_ALPHA2_CODES:
            raise ValueError(f"Unsupported BSUID country prefix: {value}")
        return normalized

    @property
    def transport_field(self) -> str:
        """Return the provider field that should carry this identifier."""
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
    stripped = value.strip()
    normalized = stripped[:2].upper() + stripped[2:] if len(stripped) >= 2 else stripped
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


class RecipientRequest(BaseModel):
    """Shared request boundary for models that accept a recipient identifier."""

    recipient: RecipientIdentifier = Field(
        ..., min_length=1, description="Recipient phone number or BSUID"
    )
    user_id: str | None = Field(
        default=None,
        description=(
            "Canonical domain identifier for the user. Opaque to Wappa — used "
            "as the key for state/cache lookups inside event handlers. Defaults "
            "to `recipient` when omitted."
        ),
    )


__all__ = [
    "BSUID_PATTERN",
    "ISO_ALPHA2_CODES",
    "PHONE_PATTERN",
    "PHONE_SANITIZE_PATTERN",
    "RecipientIdentifier",
    "RecipientRequest",
    "RecipientKind",
    "ResolvedRecipient",
    "apply_recipient_to_payload",
    "looks_like_bsuid",
    "looks_like_phone_number",
    "normalize_recipient_identifier",
    "resolve_recipient",
]
