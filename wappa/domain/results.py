"""Neutral outbound/read/control result evidence shared by every Platform.

``MessageResult`` is the private-message send result every Messenger returns;
each adapter builds it from its own wire response and keeps the native
response and normalized ``wappa_parts`` evidence in ``platform_response``. Comments, controls and reads use their own
result kinds so a comment ID never masquerades as a DM message ID and a
control success never claims a webhook exists.

Outcomes:

- ``accepted``: the provider accepted the operation (not delivery/read).
- ``rejected``: the provider or local validation refused it; safe to inspect.
- ``indeterminate``: transport/5xx/malformed success — the effect is unknown;
  do not blindly retry a send or destructive mutation.
- ``rate_limited``: a Meta rate limit stopped that part; inspect the aggregate
  before retrying after ``retry_after`` seconds. Short limits are already
  retried inside the call (``wappa.resilience.rate_limits``).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from wappa.domain.error_evidence import ErrorEvidence
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DeliveryAddresses
from wappa.domain.part_content import PartContent
from wappa.domain.user_identity import UserIdentity
from wappa.schemas.core.recipient import is_bsuid_digit_echo
from wappa.schemas.core.types import PlatformType


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MessagePart(BaseModel):
    """One normalized attempted or skipped Platform message, safe to serialize."""

    model_config = ConfigDict(extra="forbid")
    index: int
    role: str
    text: str | None = None
    content: PartContent | None = None
    message_id: str | None = None
    outcome: Literal[
        "accepted", "rejected", "indeterminate", "rate_limited", "not_attempted"
    ]
    error_code: str | None = None
    error_evidence: ErrorEvidence | None = None
    retry_after: float | None = None
    reply_to_dropped: bool = False


class AggregateOutcome(StrEnum):
    ACCEPTED = "accepted"
    PARTIALLY_ACCEPTED = "partially_accepted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"
    RATE_LIMITED = "rate_limited"


class MessageResult(BaseModel):
    """Outcome of one private-message send, neutral across Platforms.

    ``platform`` is required: an adapter always states which Platform it
    sent on. ``platform_response`` is the single native-evidence field and is
    excluded from serialization. Every send adapter adds normalized ``wappa_parts``
    evidence there, even for a single native message. The recipient evidence fields carry the
    Delivery Address evidence of ADR-0022; Platforms without BSUIDs or phone
    numbers leave them ``None``.
    """

    model_config = ConfigDict(use_enum_values=True)

    success: bool
    parts: tuple[MessagePart, ...] = ()
    error_evidence: ErrorEvidence | None = None
    platform: PlatformType
    message_id: str | None = None
    recipient: str | None = Field(
        None,
        description="Recipient identifier (BSUID if available, else phone number)",
    )
    recipient_platform_id: str | None = None
    recipient_bsuid: str | None = Field(
        None,
        description="Business Scoped User ID if message was sent to BSUID",
    )
    recipient_phone: str | None = Field(
        None,
        description="Recipient phone evidence, excluding proven BSUID digit echoes",
    )
    recipient_parent_bsuid: str | None = None
    recipient_username: str | None = None
    attempted_recipients: tuple[str, ...] = Field(
        default=(),
        description=(
            "Every Delivery Address tried, in order, when the adapter fell back "
            "(ADR-0022); empty when the first address decided the outcome"
        ),
    )
    error: str | None = None
    error_code: str | None = None
    retry_after: float | None = Field(
        None,
        description=(
            "Seconds until a retry can succeed; set only when a Meta rate "
            "limit stopped a part; inspect aggregate_outcome before retrying"
        ),
    )
    timestamp: datetime = Field(default_factory=_utc_now)
    inbox_id: str | None = None
    platform_response: dict[str, Any] | None = Field(
        default=None,
        exclude=True,
        description="Native Platform response evidence (not serialized)",
    )

    @model_validator(mode="after")
    def _exclude_bsuid_digit_echo(self) -> Self:
        if not self.recipient_phone:
            return self

        if is_bsuid_digit_echo(
            self.recipient_phone,
            self.recipient_bsuid,
            self.recipient_parent_bsuid,
            self.recipient,
        ):
            self.recipient_phone = None
        return self

    def identity(self) -> UserIdentity:
        """Inbox-qualified evidence, using the adapter's identity parser."""
        if not self.inbox_id:
            raise ValueError("Identity projection requires inbox_id")
        addresses = DeliveryAddresses.of(
            self.recipient_platform_id,
            self.recipient_bsuid,
            self.recipient_phone,
            self.recipient,
        )
        return UserIdentity(
            inbox_ref=InboxRef(
                platform=PlatformType(self.platform), inbox_id=self.inbox_id
            ),
            user_id=self.recipient_platform_id
            or self.recipient_bsuid
            or self.recipient
            or self.recipient_phone
            or "",
            addresses=addresses.model_copy(
                update={
                    "evidence": tuple(
                        value
                        for value in (self.recipient_bsuid, self.recipient_parent_bsuid)
                        if value
                    )
                }
            ),
            platform_user_id=self.recipient_platform_id,
            phone_number=self.recipient_phone,
            bsuid=self.recipient_bsuid,
            parent_bsuid=self.recipient_parent_bsuid,
            username=self.recipient_username,
        )

    @computed_field  # type: ignore[prop-decorator]  # Pydantic serializes the aggregate property.
    @property
    def aggregate_outcome(self) -> AggregateOutcome:
        return aggregate_message_outcome(self)


class OperationOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"
    RATE_LIMITED = "rate_limited"


def message_outcome(result: MessageResult) -> OperationOutcome:
    """Classify a MessageResult without changing its historical fields."""
    if result.success:
        return OperationOutcome.ACCEPTED
    if result.retry_after is not None:
        return OperationOutcome.RATE_LIMITED
    if result.error_code == "INDETERMINATE":
        return OperationOutcome.INDETERMINATE
    return OperationOutcome.REJECTED


def aggregate_message_outcome(result: MessageResult) -> AggregateOutcome:
    """Never label a partially accepted send as safe to retry as a whole."""
    outcomes = {part.outcome for part in result.parts}
    if "accepted" in outcomes and outcomes != {"accepted"}:
        return AggregateOutcome.PARTIALLY_ACCEPTED
    if "indeterminate" in outcomes:
        return AggregateOutcome.INDETERMINATE
    return AggregateOutcome(message_outcome(result).value)


class _ProviderResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False, extra="forbid")

    outcome: OperationOutcome
    error_evidence: ErrorEvidence | None = None
    platform: PlatformType
    inbox_id: str
    error: str | None = None
    error_code: str | None = None
    retry_after: float | None = None  # set with outcome rate_limited
    timestamp: datetime = Field(default_factory=_utc_now)
    platform_response: dict[str, Any] | None = Field(default=None, exclude=True)

    @property
    def success(self) -> bool:
        return self.outcome is OperationOutcome.ACCEPTED


class CommentResult(_ProviderResult):
    """Outcome of a public comment reply; identifies a Comment, never a DM."""

    comment_id: str | None = Field(
        default=None, description="Native ID of the created public reply"
    )
    parent_comment_id: str


class CommentControlOperation(StrEnum):
    HIDE = "hide"
    UNHIDE = "unhide"
    DELETE = "delete"
    ENABLE_COMMENTS = "enable_comments"
    DISABLE_COMMENTS = "disable_comments"


class ControlResult(_ProviderResult):
    """Outcome of a Comment Control; does not prove a matching webhook."""

    operation: CommentControlOperation
    resource_id: str


__all__ = [
    "CommentControlOperation",
    "CommentResult",
    "ControlResult",
    "MessageResult",
    "MessagePart",
    "AggregateOutcome",
    "aggregate_message_outcome",
    "OperationOutcome",
    "message_outcome",
]
