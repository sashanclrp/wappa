"""Universal Models for conversation events beyond new messages and statuses.

Each model keeps one meaning:

- :class:`MessageUpdateWebhook` — an existing message was edited or deleted.
- :class:`IncomingCommentWebhook` — a public Comment (regular or Live).
- :class:`MentionWebhook` — the account was mentioned in public media/comment.
- :class:`HistorySyncWebhook` — past conversations pushed by the Platform.
- :class:`InboxConnectionWebhook` — an Inbox stopped or resumed delivery.
- :class:`OutboundEchoWebhook` — a message the business itself sent, echoed back
  by the Platform (ADR-0025: one lane for WhatsApp Coexistence and Instagram).

Absent Platform evidence stays absent; nothing here fabricates a DM User,
a Comment for a media-only mention, or a message ID for a comment.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.webhook_interfaces.base_components import (
    EntryPointKind,
    EntryReferral,
    InboxBase,
    UserBase,
)

_MODEL_CONFIG = ConfigDict(extra="forbid", validate_assignment=True)


class MessageUpdateKind(StrEnum):
    EDITED = "edited"
    DELETED = "deleted"


class MessageUpdateWebhook(BaseModel):
    """A User changed an earlier message; never a new message or a status.

    One lane on every Platform (ADR-0025): WhatsApp ``edit`` / ``revoke`` and
    Instagram ``message_edit`` / unsend. For edits, ``message`` is the typed
    replacement (same models as inbound messages) and ``text`` its text.
    """

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    user: UserBase
    update_kind: MessageUpdateKind
    message_id: str = Field(description="Native ID of the affected original message")
    text: str | None = Field(
        default=None, description="Replacement text for edits; None for deletions"
    )
    message: BaseMessage | None = Field(
        default=None,
        description="Typed replacement content for edits, when the Platform sends it",
    )
    edit_count: int | None = Field(default=None, description="Provider revision count")
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def is_edit(self) -> bool:
        return self.update_kind is MessageUpdateKind.EDITED

    @property
    def is_deletion(self) -> bool:
        return self.update_kind is MessageUpdateKind.DELETED

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "message_update",
            "platform": self.platform.value,
            "update_kind": self.update_kind.value,
            "message_id": self.message_id,
            "user": self.user.user_id,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


class CommentSource(StrEnum):
    COMMENTS = "comments"
    LIVE_COMMENTS = "live_comments"


class CommentAuthor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    author_id: str | None = None
    username: str | None = None
    self_scoped_id: str | None = Field(
        default=None,
        description="Provider-supplied IGSID of the author for this account, if any",
    )


class IncomingCommentWebhook(BaseModel):
    """A public Comment or reply, including Live comments.

    ``parent_comment_ref`` is set only when the Platform supplied parent
    evidence; ``None`` does not prove the comment is top-level.
    ``is_own_comment`` lets consumers ignore their own replies (echo loops).
    """

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    comment_ref: CommentRef
    post_ref: PostRef | None = None
    source: CommentSource
    media_product_type: str | None = None
    parent_comment_ref: CommentRef | None = None
    author: CommentAuthor | None = None
    text: str | None = None
    ad_id: str | None = None
    ad_title: str | None = None
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def comment_id(self) -> str:
        return self.comment_ref.comment_id

    @property
    def is_live(self) -> bool:
        return self.source is CommentSource.LIVE_COMMENTS

    @property
    def is_reply(self) -> bool | None:
        return True if self.parent_comment_ref is not None else None

    @property
    def is_own_comment(self) -> bool:
        return bool(self.author and self.author.author_id == self.inbox.inbox_id)

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "comment",
            "platform": self.platform.value,
            "source": self.source.value,
            "comment_id": self.comment_id,
            "media_id": self.post_ref.media_id if self.post_ref else None,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


class MentionSubject(StrEnum):
    MEDIA = "media"
    COMMENT = "comment"


class MentionWebhook(BaseModel):
    """The account was mentioned publicly; a media-only mention has no Comment."""

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    subject: MentionSubject
    post_ref: PostRef
    comment_ref: CommentRef | None = None
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "mention",
            "platform": self.platform.value,
            "subject": self.subject.value,
            "media_id": self.post_ref.media_id,
            "comment_id": self.comment_ref.comment_id if self.comment_ref else None,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


class EchoOrigin(StrEnum):
    """How Wappa knows an echoed message was sent outside Wappa."""

    BUSINESS_APP = "business_app"
    """Proven not sent through Wappa: the Platform's own app, a linked device
    or another tool."""
    UNKNOWN = "unknown"
    """Wappa could not check (its sent-message registry was unavailable), so
    the echo is delivered rather than lost. It may be one of Wappa's sends."""


class OutboundEchoWebhook(BaseModel):
    """A message the business sent to ``user`` outside Wappa, echoed back.

    One lane for every Platform (ADR-0025), with a fixed Wappa filter
    (ADR-0023): echoes of messages sent through a Wappa Messenger are never
    delivered, so this hook sees only what a person sent from the Platform's
    own app (the Instagram app, the WhatsApp Business app) or another tool.
    Hosts store what arrives; they never filter Wappa's own sends.

    - WhatsApp Coexistence ``smb_message_echoes``: Meta echoes only
      Business-app messages, so no filtering is needed.
    - Instagram ``message_echoes``: Meta echoes every outbound message with
      no sender-app evidence, so Wappa drops its own using its sent-message
      registry (the IDs its sends returned).

    ``message`` uses the same typed message models as inbound messages. It is
    ``None`` only for outbound-only shapes with no inbound model (for example
    templates); ``native_type`` still names the kind.
    """

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    user: UserBase = Field(description="The User the business wrote to")
    message_id: str = Field(description="Native ID of the echoed message")
    message_type: MessageType | None = Field(
        default=None, description="Kind of the echoed message, when Wappa knows it"
    )
    native_type: str = Field(description="The Platform's own message type label")
    message: BaseMessage | None = Field(
        default=None, description="Typed content, same models as inbound messages"
    )
    origin: EchoOrigin
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def is_from_business_app(self) -> bool:
        """True when Wappa proved the message was not sent through Wappa."""
        return self.origin is EchoOrigin.BUSINESS_APP

    def get_text(self) -> str | None:
        """Text of a text echo (or a media caption), else ``None``."""
        if self.message is None:
            return None
        for attr in ("text_content", "caption"):
            value = getattr(self.message, attr, None)
            if isinstance(value, str) and value:
                return value
        return None

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "outbound_echo",
            "platform": self.platform.value,
            "origin": self.origin.value,
            "message_id": self.message_id,
            "native_type": self.native_type,
            "user": self.user.user_id,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


class HistoryDirection(StrEnum):
    INBOUND = "inbound"
    """The User sent it to the business."""
    OUTBOUND = "outbound"
    """The business sent it to the User."""


class HistoryMessage(BaseModel):
    """One past message, typed like a live message (ADR-0025)."""

    model_config = _MODEL_CONFIG
    message_id: str
    direction: HistoryDirection
    timestamp: datetime
    native_type: str
    message_type: MessageType | None = None
    message: BaseMessage | None = Field(
        default=None, description="Typed content, same models as inbound messages"
    )
    status: str | None = Field(
        default=None, description="Delivery state the Platform recorded, if any"
    )


class HistoryThread(BaseModel):
    """Past messages exchanged with one User, oldest first."""

    model_config = _MODEL_CONFIG
    user: UserBase
    messages: tuple[HistoryMessage, ...] = ()


class HistorySyncWebhook(BaseModel):
    """Past conversations the Platform pushed (ADR-0025 history backfill).

    The push half of one backfill contract: WhatsApp Coexistence ``history``
    chunks arrive here. Platforms that only offer pulls (Instagram) expose
    the same ``HistoryThread`` through the ``IConversationHistoryReader``
    capability instead. ``progress`` is the Platform's 0-100 sync progress.
    """

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    threads: tuple[HistoryThread, ...] = ()
    phase: int | None = None
    chunk_order: int | None = None
    progress: int | None = None
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def message_count(self) -> int:
        return sum(len(t.messages) for t in self.threads)

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "history_sync",
            "platform": self.platform.value,
            "threads": len(self.threads),
            "messages": self.message_count,
            "phase": self.phase,
            "chunk_order": self.chunk_order,
            "progress": self.progress,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


class InboxConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    """The Inbox stopped receiving and sending (offboarded, app removed)."""
    RECONNECTED = "reconnected"
    """The Inbox resumed after a disconnection."""


class InboxConnectionWebhook(BaseModel):
    """An Inbox's connection to Wappa changed (ADR-0025, ADR-0026).

    WhatsApp Coexistence ``account_offboarded`` / ``account_reconnected``
    arrive here, so a Host deactivates or restores the Inbox the same way.
    Instagram has no emitter: Meta sends no deauthorize callback for the
    Unified Login grants ``InstagramConnector`` creates.
    """

    model_config = _MODEL_CONFIG
    inbox: InboxBase
    state: InboxConnectionState
    reason: str | None = None
    account_id: str | None = Field(
        default=None, description="Platform Account (WABA, Instagram account)"
    )
    timestamp: datetime
    platform: PlatformType
    webhook_id: str
    raw_webhook_data: dict | None = Field(default=None, exclude=True)

    @property
    def is_disconnected(self) -> bool:
        return self.state is InboxConnectionState.DISCONNECTED

    def get_summary(self) -> dict[str, Any]:
        return {
            "webhook_type": "inbox_connection",
            "platform": self.platform.value,
            "state": self.state.value,
            "reason": self.reason,
            "inbox": self.inbox.get_inbox_key(),
        }

    def set_raw_webhook_data(self, raw_data: dict) -> None:
        self.raw_webhook_data = raw_data


__all__ = [
    "HistoryDirection",
    "HistoryMessage",
    "HistorySyncWebhook",
    "HistoryThread",
    "InboxConnectionState",
    "InboxConnectionWebhook",
    "EntryPointKind",
    "CommentAuthor",
    "EchoOrigin",
    "CommentSource",
    "EntryReferral",
    "IncomingCommentWebhook",
    "MentionSubject",
    "MentionWebhook",
    "MessageUpdateKind",
    "OutboundEchoWebhook",
    "MessageUpdateWebhook",
]
