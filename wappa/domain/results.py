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
- ``rate_limited``: a Meta rate limit stopped it and nothing was delivered;
  safe to retry after ``retry_after`` seconds. Short limits are already
  retried inside the call (``wappa.resilience.rate_limits``).
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wappa.schemas.core.recipient import looks_like_bsuid
from wappa.schemas.core.types import PlatformType


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
    platform: PlatformType
    message_id: str | None = None
    recipient: str | None = Field(
        None,
        description="Recipient identifier (BSUID if available, else phone number)",
    )
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
            "limit stopped the send (nothing was delivered)"
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

        phone = self.recipient_phone.strip().removeprefix("+")
        for identifier in (
            self.recipient_bsuid,
            self.recipient_parent_bsuid,
            self.recipient,
        ):
            if identifier and looks_like_bsuid(identifier):
                suffix = identifier.strip().rsplit(".", 1)[-1]
                if suffix.isascii() and suffix.isdigit() and phone == suffix:
                    self.recipient_phone = None
                    break
        return self


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


class _ProviderResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False, extra="forbid")

    outcome: OperationOutcome
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
    "OperationOutcome",
    "message_outcome",
]
