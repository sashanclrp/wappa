"""Explicit Inbox-qualified destinations and public-conversation references.

A target says *where* an outbound operation goes and *which Inbox* may use it.
Targets never infer visibility: a :class:`PrivateReply` is a private message
addressed through a comment, a public comment reply is a separate operation
(``reply_comment``) and an ordinary DM is a :class:`DirectMessage`.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wappa.domain.inbox.identity import InboxRef
from wappa.schemas.core.types import PlatformType


def _nonblank(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


class UnsupportedOperationError(NotImplementedError):
    """This Platform adapter does not implement the requested operation."""


class TargetInboxMismatchError(ValueError):
    """A target or reference belongs to a different Inbox than the adapter."""


class DeliveryAddresses(BaseModel):
    """Every known Delivery Address of one User (ADR-0019).

    Callers only state what they know (WhatsApp: BSUID and/or phone; Instagram:
    the scoped ID). The Platform adapter decides the order and when to move on
    to the next address; Host code never codes that logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    values: tuple[str, ...] = Field(min_length=1)

    @field_validator("values", mode="before")
    @classmethod
    def _coerce(cls, values: object) -> object:
        # A serialized target (JSON lists) must validate back unchanged.
        return tuple(values) if isinstance(values, list) else values

    @field_validator("values")
    @classmethod
    def _clean(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        cleaned: list[str] = []
        for value in values:
            value = _nonblank(value, "Delivery Address").strip()
            if value not in cleaned:
                cleaned.append(value)
        return tuple(cleaned)

    @classmethod
    def of(cls, *addresses: str | None) -> "DeliveryAddresses":
        """Build from whatever is known; ``None`` and blanks are skipped."""
        known = tuple(a for a in addresses if a is not None and a.strip())
        if not known:
            raise ValueError("At least one Delivery Address is required")
        return cls(values=known)

    @property
    def primary(self) -> str:
        return self.values[0]


class DirectMessage(BaseModel):
    """A User's Delivery Addresses bound to the Inbox allowed to use them."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    kind: Literal["direct_message"] = "direct_message"
    inbox_ref: InboxRef
    addresses: DeliveryAddresses

    @property
    def recipient_id(self) -> str:
        """First known address (read-only evidence for logs and middleware)."""
        return self.addresses.primary

    @property
    def address(self) -> str:
        """Native address evidence for logs/middleware."""
        return self.addresses.primary

    def _check_inbox(self, inbox_ref: InboxRef) -> None:
        if self.inbox_ref != inbox_ref:
            raise TargetInboxMismatchError(
                "DirectMessage target belongs to a different Inbox"
            )

    def resolve(self, inbox_ref: InboxRef) -> str:
        """The single address for Platforms with one address per User."""
        self._check_inbox(inbox_ref)
        return self.addresses.primary

    def resolve_all(self, inbox_ref: InboxRef) -> tuple[str, ...]:
        """Every known address; the Platform adapter orders and tries them."""
        self._check_inbox(inbox_ref)
        return self.addresses.values


class CommentRef(BaseModel):
    """Inbox-qualified native identifier of one public Comment.

    A reference is not the comment's content or author. A comment ID is never
    a DM message ID.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    inbox_ref: InboxRef
    comment_id: str = Field(min_length=1)

    @field_validator("comment_id")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        return _nonblank(value, "CommentRef comment_id")

    def resolve(self, inbox_ref: InboxRef) -> str:
        if self.inbox_ref != inbox_ref:
            raise TargetInboxMismatchError("Comment belongs to a different Inbox")
        return self.comment_id


class PostRef(BaseModel):
    """Inbox-qualified native identifier of Platform media (post, Reel, Live).

    It does not imply that caption, bytes or metadata are accessible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    inbox_ref: InboxRef
    media_id: str = Field(min_length=1)

    @field_validator("media_id")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        return _nonblank(value, "PostRef media_id")

    def resolve(self, inbox_ref: InboxRef) -> str:
        if self.inbox_ref != inbox_ref:
            raise TargetInboxMismatchError("Media belongs to a different Inbox")
        return self.media_id


class PrivateReply(BaseModel):
    """Instagram-only private message addressed through a triggering Comment.

    Meta allows one private reply per comment inside the provider's window; a
    normal DM follow-up requires the User to answer first.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    kind: Literal["private_reply"] = "private_reply"
    comment_ref: CommentRef

    @model_validator(mode="after")
    def _instagram_only(self) -> "PrivateReply":
        if self.comment_ref.inbox_ref.platform is not PlatformType.INSTAGRAM:
            raise ValueError("PrivateReply is only implemented for Instagram")
        return self

    @property
    def inbox_ref(self) -> InboxRef:
        return self.comment_ref.inbox_ref

    @property
    def address(self) -> str:
        return f"comment:{self.comment_ref.comment_id}"

    def resolve(self, inbox_ref: InboxRef) -> str:
        """Return the native comment ID used as ``recipient.comment_id``."""
        return self.comment_ref.resolve(inbox_ref)


MessageTarget = DirectMessage | PrivateReply
"""Every outbound private destination accepted by ``IMessenger`` sends."""


def require_direct_message(target: MessageTarget, operation: str) -> DirectMessage:
    """Reject a PrivateReply for operations that only support ordinary DMs."""
    if isinstance(target, DirectMessage):
        return target
    raise UnsupportedOperationError(
        f"{operation} does not accept a PrivateReply target; private replies "
        "are text-only (send_text)"
    )


__all__ = [
    "CommentRef",
    "DeliveryAddresses",
    "DirectMessage",
    "MessageTarget",
    "PostRef",
    "PrivateReply",
    "TargetInboxMismatchError",
    "UnsupportedOperationError",
    "require_direct_message",
]
