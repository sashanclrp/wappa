"""Focused, optional conversation capabilities beside the Messenger facade.

These are not methods every Messenger must implement. A Messenger advertises
them through ``IMessenger.capability(kind)``; callers receive ``None`` (or
``UnsupportedOperationError`` from ``require_capability``) when the Platform
adapter has no implementation. Host policy decides whether and when to call
them — Wappa ships the mechanism only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.domain.results import CommentResult, ControlResult


class ReadOutcome(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ACCESS_DENIED = "access_denied"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class ReadResult[T](BaseModel):
    """Explicit read outcome; ``value`` is present only when ``found``."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    outcome: ReadOutcome
    value: T | None = None
    error: str | None = None
    error_code: str | None = None

    @property
    def found(self) -> bool:
        return self.outcome is ReadOutcome.FOUND and self.value is not None


class ContentPage[T](BaseModel):
    """One page of a provider collection; ``next_cursor`` continues it."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    items: tuple[T, ...] = ()
    next_cursor: str | None = None

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None


class PostChild(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    media_id: str
    media_type: str | None = None
    media_url: str | None = None
    thumbnail_url: str | None = None
    permalink: str | None = None


class PostContent(BaseModel):
    """Accessible media metadata. Absent fields were not returned/authorized."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    post_ref: PostRef
    media_type: str | None = None
    media_product_type: str | None = None
    caption: str | None = None
    permalink: str | None = None
    media_url: str | None = None
    thumbnail_url: str | None = None
    timestamp: datetime | None = None
    username: str | None = None
    comments_count: int | None = None
    like_count: int | None = None
    is_comment_enabled: bool | None = None
    children: tuple[PostChild, ...] = ()
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class CommentContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    comment_ref: CommentRef
    text: str | None = None
    timestamp: datetime | None = None
    author_id: str | None = None
    author_username: str | None = None
    parent_comment_id: str | None = None
    media_id: str | None = None
    hidden: bool | None = None
    like_count: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class MediaBytes(BaseModel):
    """Bounded downloaded bytes and the evidence that describes them."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content: bytes = Field(repr=False)
    content_type: str | None = None
    size: int
    source_host: str


class ICommentControls(ABC):
    """Public comment actions: reply, hide/unhide/delete, media commenting.

    A Platform-only capability (ADR-0016): WhatsApp has no comments. Private
    replies to a commenter use the shared ``send_text(PrivateReply(...))``.
    """

    @abstractmethod
    async def reply_comment(
        self, comment_ref: CommentRef, text: str
    ) -> CommentResult: ...

    @abstractmethod
    async def hide_comment(self, comment_ref: CommentRef) -> ControlResult: ...

    @abstractmethod
    async def unhide_comment(self, comment_ref: CommentRef) -> ControlResult: ...

    @abstractmethod
    async def delete_comment(self, comment_ref: CommentRef) -> ControlResult: ...

    @abstractmethod
    async def set_comments_enabled(
        self, post_ref: PostRef, enabled: bool
    ) -> ControlResult: ...


class IConversationContentReader(ABC):
    """Explicit post/comment reads; never called by processors or dispatch."""

    @abstractmethod
    async def get_post(self, post_ref: PostRef) -> ReadResult[PostContent]: ...

    @abstractmethod
    async def get_comment(
        self, comment_ref: CommentRef
    ) -> ReadResult[CommentContent]: ...

    @abstractmethod
    async def list_comments(
        self, post_ref: PostRef, *, after: str | None = None, limit: int = 25
    ) -> ReadResult[ContentPage[CommentContent]]: ...

    @abstractmethod
    async def list_replies(
        self, comment_ref: CommentRef, *, after: str | None = None, limit: int = 25
    ) -> ReadResult[ContentPage[CommentContent]]: ...


__all__ = [
    "CommentContent",
    "ContentPage",
    "ICommentControls",
    "IConversationContentReader",
    "MediaBytes",
    "PostChild",
    "PostContent",
    "ReadOutcome",
    "ReadResult",
]
