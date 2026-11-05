"""Neutral outbound/read/control result evidence shared by every Platform.

``MessageResult`` remains the private-message send result (its historical
module is the WhatsApp package; import it from here). Comments, controls and
reads use their own result kinds so a comment ID never masquerades as a DM
message ID and a control success never claims a webhook exists.

Outcomes:

- ``accepted``: the provider accepted the operation (not delivery/read).
- ``rejected``: the provider or local validation refused it; safe to inspect.
- ``indeterminate``: transport/5xx/malformed success — the effect is unknown;
  do not blindly retry a send or destructive mutation.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.messaging.whatsapp.models.basic_models import MessageResult
from wappa.schemas.core.types import PlatformType


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OperationOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INDETERMINATE = "indeterminate"


def message_outcome(result: MessageResult) -> OperationOutcome:
    """Classify a MessageResult without changing its historical fields."""
    if result.success:
        return OperationOutcome.ACCEPTED
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
