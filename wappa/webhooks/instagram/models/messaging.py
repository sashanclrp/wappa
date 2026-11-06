"""Instagram ``entry[].messaging[]`` wire models: message, read, postback, reaction, edit."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from wappa.webhooks.instagram.fields import INSTAGRAM_MESSAGING_KEYS

from .common import (
    InstagramAttachment,
    InstagramIdentity,
    InstagramQuickReplyPayload,
    InstagramReferral,
    InstagramReplyTo,
)


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


def is_echo(event: InstagramMessagingEvent, account_id: str) -> bool:
    message = event.message
    return bool(
        event.sender.id == account_id
        or (message and (message.is_echo or message.is_self))
    )
