"""Inbox-qualified identity evidence; durable reconciliation belongs to the Host."""

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DeliveryAddresses
from wappa.schemas.core.recipient import is_bsuid_digit_echo


class UserIdentity(BaseModel):
    """The recommended User ID and every known address, with optional evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    inbox_ref: InboxRef
    user_id: str
    addresses: DeliveryAddresses
    platform_user_id: str | None = None
    phone_number: str | None = None
    bsuid: str | None = None
    parent_bsuid: str | None = None
    username: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _phone_evidence(cls, value: Any) -> Any:
        if (
            isinstance(value, dict)
            and (phone := value.get("phone_number"))
            and is_bsuid_digit_echo(
                phone, value.get("bsuid"), value.get("parent_bsuid")
            )
        ):
            return dict(value, phone_number=None)
        return value


def opaque_identity(
    inbox_ref: InboxRef, user_id: str, addresses: tuple[str, ...]
) -> UserIdentity:
    """Default for Platforms with native scoped IDs and no phone evidence."""
    return UserIdentity(
        inbox_ref=inbox_ref,
        user_id=user_id,
        addresses=DeliveryAddresses.of(*addresses),
        platform_user_id=addresses[0],
    )
