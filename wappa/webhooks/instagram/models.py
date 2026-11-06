"""Instagram webhook envelope and message-family models (Unified Login).

Sources (fetched 2026-11-03, Graph v26.0): Instagram webhooks examples/fields,
messaging-api, private-replies and comment-moderation pages. The envelope is
``object: "instagram"`` with ``entry[].messaging[]`` (DM events) and/or
``entry[].changes[]`` (``comments``, ``live_comments``, ``mentions`` and
extension fields). Provider extensions are retained but never promote an
event into a different lane (echo/deletion/edit/postback stay separate).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from wappa.schemas.core.types import (
    InteractiveType,
    MediaType,
    MessageType,
    PlatformType,
    UniversalMessageData,
)
from wappa.webhooks.core.base_message import (
    BaseAudioMessage,
    BaseDocumentMessage,
    BaseImageMessage,
    BaseInteractiveMessage,
    BaseMessage,
    BaseMessageContext,
    BaseReactionMessage,
    BaseTextMessage,
    BaseVideoMessage,
)

NativeID = str

# Built-in Instagram fields. Extensions may not register these names.
INSTAGRAM_MESSAGING_KEYS: frozenset[str] = frozenset(
    {"message", "read", "postback", "referral", "reaction", "message_edit"}
)
INSTAGRAM_CHANGE_FIELDS: frozenset[str] = frozenset(
    {"comments", "live_comments", "mentions"}
)
INSTAGRAM_BUILTIN_FIELDS: frozenset[str] = frozenset(
    {
        "messages",
        "messaging_seen",
        "messaging_postbacks",
        "messaging_referral",
        "message_edit",
        "message_reactions",
        "message_echoes",
        "messaging_optins",
        "messaging_handover",
        "standby",
    }
    | INSTAGRAM_CHANGE_FIELDS
)
"""Reserved Instagram field names (handled, excluded or core subscriptions)."""


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


class InstagramMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    mid: str | None = None
    text: str | None = None
    is_echo: bool = False
    is_deleted: bool = False
    is_self: bool = False
    is_unsupported: bool = False
    attachments: list[InstagramAttachment] | None = None
    quick_reply: InstagramQuickReplyPayload | None = None
    reply_to: InstagramReplyTo | None = None
    referral: InstagramReferral | None = None


class InstagramSeen(BaseModel):
    model_config = ConfigDict(extra="allow")
    mid: str = Field(min_length=1)


class InstagramPostback(BaseModel):
    model_config = ConfigDict(extra="allow")
    mid: str | None = None
    title: str | None = None
    payload: str | None = None
    referral: InstagramReferral | None = None


class InstagramMessageEdit(BaseModel):
    model_config = ConfigDict(extra="allow")
    mid: str = Field(min_length=1)
    text: str | None = None
    num_edit: int | None = None


class InstagramReaction(BaseModel):
    """``message_reactions`` evidence: a User reacted to (or unreacted) a message."""

    model_config = ConfigDict(extra="allow")
    mid: str = Field(min_length=1, description="The message the reaction applies to")
    action: str = Field(description="react or unreact")
    reaction: str | None = Field(default=None, description="Reaction name, e.g. love")
    emoji: str | None = None


class InstagramMessagingEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    sender: InstagramIdentity
    recipient: InstagramIdentity
    timestamp: PositiveInt
    message: InstagramMessage | None = None
    read: InstagramSeen | None = None
    postback: InstagramPostback | None = None
    referral: InstagramReferral | None = None
    reaction: InstagramReaction | None = None
    message_edit: InstagramMessageEdit | None = None

    @model_validator(mode="after")
    def _unambiguous(self) -> InstagramMessagingEvent:
        present = [k for k in INSTAGRAM_MESSAGING_KEYS if getattr(self, k) is not None]
        if len(present) > 1:
            raise ValueError(
                f"Instagram messaging event carries several kinds: {sorted(present)}"
            )
        return self


class InstagramChange(BaseModel):
    """One ``changes[]`` item; ``value`` is parsed per field by the processor."""

    model_config = ConfigDict(extra="allow")
    field: str = Field(min_length=1)
    value: dict[str, Any]


class InstagramEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1)
    time: int | None = None
    messaging: list[InstagramMessagingEvent] = Field(default_factory=list)
    changes: list[InstagramChange] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flat_change(cls, data: Any) -> Any:
        # The Instagram Login doc example shows field/value directly on entry.
        if isinstance(data, dict) and "field" in data and "value" in data:
            data = dict(data)
            change = {"field": data.pop("field"), "value": data.pop("value")}
            data["changes"] = [*data.get("changes", []), change]
        return data

    @model_validator(mode="after")
    def _has_events(self) -> InstagramEntry:
        if not self.messaging and not self.changes:
            raise ValueError("Instagram entry carries no messaging events or changes")
        return self


# ── Change values ────────────────────────────────────────────────────────


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


# ── Envelope ─────────────────────────────────────────────────────────────


class InstagramWebhook(BaseModel):
    """The ``object: instagram`` callback envelope; no container ABC."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, validate_assignment=True
    )

    object: Literal["instagram"]
    entry: list[InstagramEntry] = Field(min_length=1)


def is_echo(event: InstagramMessagingEvent, account_id: str) -> bool:
    message = event.message
    return bool(
        event.sender.id == account_id
        or (message and (message.is_echo or message.is_self))
    )


# ── Normalized message classes ───────────────────────────────────────────


class InstagramMessageContext(BaseMessageContext):
    """Reply context: an earlier message or a story the User replied to."""

    model_config = ConfigDict(extra="allow")
    reply_to_message_id: str | None = None
    story_id: str | None = None
    story_url: str | None = None

    @property
    def original_message_id(self) -> str | None:
        return self.reply_to_message_id

    @property
    def original_sender_id(self) -> str | None:
        return None

    @property
    def is_reply(self) -> bool:
        return self.reply_to_message_id is not None or self.story_id is not None

    @property
    def is_forward(self) -> bool:
        return False

    @property
    def is_story_reply(self) -> bool:
        return self.story_id is not None or self.story_url is not None

    def to_universal_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class _InstagramMessageBase(BaseMessage):
    """Shared identity for every Instagram User message."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)
    id: str
    sender: str
    account_id: str
    timestamp_ms: PositiveInt
    context: InstagramMessageContext | None = None

    @classmethod
    def from_platform_data(cls, data: dict[str, Any], **kwargs: Any) -> Any:
        return cls.model_validate(data)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    @property
    def message_id(self) -> str:
        return self.id

    @property
    def sender_id(self) -> str:
        return self.sender

    @property
    def timestamp(self) -> int:
        return self.timestamp_ms // 1000

    @property
    def conversation_id(self) -> str:
        return self.sender

    def has_context(self) -> bool:
        return self.context is not None

    def get_context(self) -> BaseMessageContext | None:
        return self.context

    def get_platform_data(self) -> dict[str, Any]:
        return self.model_dump()

    def _universal(self, **extra: Any) -> UniversalMessageData:
        data: dict[str, Any] = {
            "platform": self.platform.value,
            "message_type": self.message_type.value,
            "message_id": self.id,
            "sender_id": self.sender,
            "timestamp": self.timestamp,
            **{k: v for k, v in extra.items() if v is not None},
        }
        return data


class InstagramTextMessage(_InstagramMessageBase, BaseTextMessage):
    """Text, including story replies (``context.is_story_reply``)."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    text: str

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def is_reply(self) -> bool:
        return bool(self.context and self.context.is_reply)

    @property
    def is_forwarded(self) -> bool:
        return False

    def get_reply_context(self) -> tuple[str | None, str | None]:
        if self.context is None:
            return None, None
        return self.context.reply_to_message_id, None

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(text=self.text)


class InstagramButtonReplyMessage(_InstagramMessageBase, BaseInteractiveMessage):
    """A postback button tap, normalized like a WhatsApp ``button_reply``.

    Instagram delivers it on ``messaging_postbacks`` with no visible message;
    Wappa presents it as an interactive message (ADR-0025) so Hosts read one
    selection shape on every Platform.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    title: str
    payload: str

    @property
    def interactive_type(self) -> InteractiveType:
        return InteractiveType.BUTTON_REPLY

    @property
    def selected_option_id(self) -> str:
        return self.payload

    @property
    def selected_option_title(self) -> str:
        return self.title

    @property
    def text_content(self) -> str:
        return self.title

    @property
    def original_message_id(self) -> str:
        return ""

    @property
    def is_button_reply(self) -> bool:
        return True

    @property
    def is_list_reply(self) -> bool:
        return False

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(text=self.title, selection=self.payload)


class InstagramQuickReplyMessage(_InstagramMessageBase, BaseInteractiveMessage):
    """A quick-reply selection: text the User saw plus the action payload.

    One native event → one InboundMessageWebhook; never also an Interaction.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    text: str
    payload: str

    @property
    def interactive_type(self) -> InteractiveType:
        return InteractiveType.QUICK_REPLY

    @property
    def selected_option_id(self) -> str:
        return self.payload

    @property
    def selected_option_title(self) -> str:
        return self.text

    @property
    def text_content(self) -> str:
        return self.text

    @property
    def original_message_id(self) -> str:
        return ""

    @property
    def is_button_reply(self) -> bool:
        return False

    @property
    def is_list_reply(self) -> bool:
        return False

    @property
    def is_quick_reply(self) -> bool:
        return True

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(text=self.text, selection=self.payload)


class _InstagramAttachmentMixin(_InstagramMessageBase):
    """Media evidence is a provider CDN URL, not a WhatsApp media ID."""

    attachments: tuple[InstagramAttachment, ...] = Field(min_length=1)
    text: str | None = None

    @property
    def primary(self) -> InstagramAttachment:
        return self.attachments[0]

    @property
    def url(self) -> str | None:
        return self.primary.url

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(a.url for a in self.attachments if a.url)

    @property
    def attachment_type(self) -> str:
        return self.primary.type

    @property
    def media_id(self) -> str:
        # Instagram supplies no reusable media ID; the URL is the reference.
        return self.url or ""

    @property
    def file_size(self) -> int | None:
        return None

    @property
    def caption(self) -> str | None:
        return self.text

    def get_download_info(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "urls": list(self.urls),
            "requires_platform_auth": False,
            "may_expire": True,
        }

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(
            attachment_type=self.attachment_type, url=self.url, text=self.text
        )


class InstagramImageMessage(_InstagramAttachmentMixin, BaseImageMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        # Nominal: Instagram webhooks carry no MIME; MediaBytes has the real one.
        return MediaType.IMAGE_JPEG

    @property
    def is_sticker(self) -> bool:
        return bool(self.primary.payload and self.primary.payload.sticker_id)


class InstagramVideoMessage(_InstagramAttachmentMixin, BaseVideoMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO_MP4

    @property
    def duration(self) -> int | None:
        return None

    @property
    def dimensions(self) -> tuple[int, int] | None:
        return None


class InstagramAudioMessage(_InstagramAttachmentMixin, BaseAudioMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO_AAC

    @property
    def is_voice_message(self) -> bool:
        return True

    @property
    def duration(self) -> int | None:
        return None


class InstagramFileMessage(_InstagramAttachmentMixin, BaseDocumentMessage):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def media_type(self) -> MediaType:
        return MediaType.DOCUMENT_PDF

    @property
    def filename(self) -> str | None:
        return self.primary.payload.title if self.primary.payload else None

    @property
    def file_extension(self) -> str | None:
        name = self.filename
        return name.rsplit(".", 1)[-1].lower() if name and "." in name else None


class InstagramShareMessage(_InstagramAttachmentMixin):
    """Shared post/Reel/story or a story mention delivered as a DM.

    ``shared_media_id`` is set only when the provider supplied it; a URL-only
    share stays processable and is not resolved here.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    @property
    def message_type(self) -> MessageType:
        if self.attachment_type == "story_mention":
            return MessageType.STORY_MENTION
        return MessageType.SHARE

    @property
    def is_story_mention(self) -> bool:
        return self.attachment_type == "story_mention"

    @property
    def shared_media_id(self) -> str | None:
        payload = self.primary.payload
        if payload is None:
            return None
        return payload.ig_post_media_id or payload.reel_video_id

    @property
    def title(self) -> str | None:
        return self.primary.payload.title if self.primary.payload else None

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(
            attachment_type=self.attachment_type,
            url=self.url,
            shared_media_id=self.shared_media_id,
            text=self.text,
        )


ATTACHMENT_CLASSES: dict[str, type[_InstagramAttachmentMixin]] = {
    "image": InstagramImageMessage,
    "video": InstagramVideoMessage,
    "audio": InstagramAudioMessage,
    "file": InstagramFileMessage,
    "share": InstagramShareMessage,
    "ig_post": InstagramShareMessage,
    "ig_reel": InstagramShareMessage,
    "reel": InstagramShareMessage,
    "story": InstagramShareMessage,
    "ig_story": InstagramShareMessage,
    "story_mention": InstagramShareMessage,
}
"""Implemented inbound attachment types; others take the unsupported lane."""


class InstagramReactionMessage(_InstagramMessageBase, BaseReactionMessage):
    """A User reacted to (or removed a reaction from) a message, ADR-0025 shape.

    Instagram gives a reaction no message ID of its own, so ``id`` is
    ``reaction:<target mid>:<timestamp ms>``.
    """

    target_mid: str
    action: str
    reaction_name: str | None = None
    emoji_value: str | None = None

    @property
    def target_message_id(self) -> str:
        return self.target_mid

    @property
    def emoji(self) -> str:
        return "" if self.is_removal else (self.emoji_value or "")

    @property
    def is_removal(self) -> bool:
        return self.action == "unreact"

    def to_universal_dict(self) -> UniversalMessageData:
        return self._universal(
            target_message_id=self.target_mid,
            emoji=self.emoji,
            is_removal=self.is_removal,
        )
