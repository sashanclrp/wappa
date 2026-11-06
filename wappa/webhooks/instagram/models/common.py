"""Instagram wire values shared by messaging events: identity, attachments, referrals.

Sources (fetched 2026-11-03, Graph v26.0): Instagram webhooks examples/fields,
messaging-api, private-replies and comment-moderation pages.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

NativeID = str


class InstagramIdentity(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    id: NativeID = Field(min_length=1)


class InstagramTemplateButton(BaseModel):
    """A button inside an echoed card (``postback`` payload or ``web_url``)."""

    model_config = ConfigDict(extra="allow")
    type: str | None = None
    title: str | None = None
    payload: str | None = None
    url: str | None = None


class InstagramTemplateElement(BaseModel):
    """One card of an echoed generic template (live echo, 2026-11-05)."""

    model_config = ConfigDict(extra="allow")
    title: str | None = None
    subtitle: str | None = None
    image_url: str | None = None
    buttons: list[InstagramTemplateButton] = Field(default_factory=list)


class InstagramGenericTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")
    elements: list[InstagramTemplateElement] = Field(default_factory=list)


class InstagramAttachmentPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    generic: InstagramGenericTemplate | None = None  # echo of a card/carousel
    url: str | None = None
    title: str | None = None
    ig_post_media_id: str | None = None
    reel_video_id: str | None = None
    sticker_id: int | str | None = None


class InstagramAttachment(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = Field(min_length=1)
    payload: InstagramAttachmentPayload | None = None

    @property
    def url(self) -> str | None:
        return self.payload.url if self.payload else None


class InstagramStoryReference(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    url: str | None = None
    link_sticker_url: str | None = None


class InstagramReplyTo(BaseModel):
    model_config = ConfigDict(extra="allow")
    mid: str | None = None
    story: InstagramStoryReference | None = None


class InstagramQuickReplyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    payload: str


class InstagramAdsContext(BaseModel):
    model_config = ConfigDict(extra="allow")
    ad_title: str | None = None
    photo_url: str | None = None
    video_url: str | None = None
    post_id: str | None = None
    product_id: str | None = None


class InstagramReferral(BaseModel):
    model_config = ConfigDict(extra="allow")
    ref: str | None = None
    source: str | None = None
    type: str | None = None
    ad_id: str | None = None
    ads_context_data: InstagramAdsContext | None = None
