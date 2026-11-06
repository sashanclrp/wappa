"""Instagram ``changes[]`` value models for comments, live comments and mentions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InstagramCommentAuthor(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    username: str | None = None
    self_ig_scoped_id: str | None = None


class InstagramCommentMedia(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    media_product_type: str | None = None
    ad_id: str | None = None
    ad_title: str | None = None
    original_media_id: str | None = None


class InstagramCommentValue(BaseModel):
    """``comments``/``live_comments`` value; accepts ``id`` or ``comment_id``."""

    model_config = ConfigDict(extra="allow")
    id: str | None = None
    comment_id: str | None = None
    parent_id: str | None = None
    text: str | None = None
    from_: InstagramCommentAuthor | None = Field(default=None, alias="from")
    media: InstagramCommentMedia | None = None

    @property
    def native_comment_id(self) -> str:
        value = self.comment_id or self.id
        if not value:
            raise ValueError("Instagram comment change has no comment ID")
        return value


class InstagramMentionValue(BaseModel):
    model_config = ConfigDict(extra="allow")
    media_id: str = Field(min_length=1)
    comment_id: str | None = None
