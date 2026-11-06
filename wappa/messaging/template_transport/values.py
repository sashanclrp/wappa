"""Template transport values: enums and normalized recipients."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wappa.schemas.core.recipient import RecipientKind, resolve_recipient


class TemplateTransportOutcome(StrEnum):
    """What Wappa can prove about one provider call."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    INDETERMINATE = "indeterminate"


class TemplateAddressKind(StrEnum):
    """Supported provider-facing Template destination kinds."""

    PHONE_NUMBER = "phone_number"
    BSUID = "bsuid"


class TemplateCategory(StrEnum):
    """Template category used by the platform for endpoint selection."""

    MARKETING = "marketing"
    UTILITY = "utility"
    AUTHENTICATION = "authentication"


class TemplateMediaType(StrEnum):
    """Supported media-header kinds."""

    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


class TemplateAuthenticationMethod(StrEnum):
    """OTP button method an approved Authentication Template was created with.

    Meta rewrites an ``OTP`` button to a ``URL`` button at template creation,
    so all three methods send the same button component and differ only in how
    the recipient's device consumes the code: ``copy_code`` writes it to the
    clipboard, ``one_tap`` hands it to a registered app on tap, and
    ``zero_tap`` broadcasts it without any tap. The device-side handshake and
    ``supported_apps`` metadata belong to template creation and to the Host
    Application's mobile app, never to this send.
    """

    ONE_TAP = "one_tap"
    ZERO_TAP = "zero_tap"
    COPY_CODE = "copy_code"


class TemplateRoutingPolicy(StrEnum):
    """Explicit endpoint policy for a Template call."""

    CATEGORY_DEFAULT = "category_default"
    CLOUD_MESSAGES_FALLBACK = "cloud_messages_fallback"


class TemplateEndpoint(StrEnum):
    MESSAGES = "messages"
    MARKETING_MESSAGES = "marketing_messages"


class TemplateRoutingReason(StrEnum):
    CATEGORY_DEFAULT = "category_default"
    EXPLICIT_MARKETING_FALLBACK = "explicit_marketing_fallback"


class PhoneNumberTemplateRecipient(BaseModel):
    """A normalized phone number sent through Meta's ``to`` field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["phone_number"] = "phone_number"
    value: str

    @field_validator("value")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        recipient = resolve_recipient(value)
        if recipient.kind is not RecipientKind.PHONE_NUMBER:
            raise ValueError("A phone_number recipient must contain a phone number")
        return recipient.transport_value


class BsuidTemplateRecipient(BaseModel):
    """A normalized regular or parent BSUID sent through Meta's ``recipient`` field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["bsuid"] = "bsuid"
    value: str

    @field_validator("value")
    @classmethod
    def normalize_bsuid(cls, value: str) -> str:
        recipient = resolve_recipient(value)
        if recipient.kind is not RecipientKind.BSUID:
            raise ValueError("A bsuid recipient must contain a regular or parent BSUID")
        return recipient.transport_value


TemplateTransportRecipient = Annotated[
    PhoneNumberTemplateRecipient | BsuidTemplateRecipient,
    Field(discriminator="kind"),
]
