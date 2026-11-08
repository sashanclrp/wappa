"""Typed universal wire projections shared by all inbound adapters.

Native fields are available only through get_platform_data(), never here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .core import BaseMessage, BaseMessageContext
    from .interactive import BaseInteractiveMessage
    from .media import BaseMediaMessage
    from .reaction import BaseReactionMessage
    from .text import BaseTextMessage


class ContextProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    original_message_id: str | None
    original_sender_id: str | None
    is_reply: bool
    is_forward: bool


class MessageProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str
    message_type: str
    message_id: str
    sender_id: str
    conversation_id: str
    conversation_type: str
    timestamp: int
    processed_at: str
    has_context: bool
    context: ContextProjection | None


class TextProjection(MessageProjection):
    content: str
    text_length: int
    is_reply: bool
    is_forwarded: bool
    is_frequently_forwarded: bool | None


class SelectionProjection(MessageProjection):
    interactive_type: str
    selected_option_id: str | None
    selected_option_title: str | None
    original_message_id: str | None
    is_button_reply: bool
    is_list_reply: bool
    is_quick_reply: bool


class MediaProjection(MessageProjection):
    media_id: str
    media_family: str
    media_type: str  # historical nominal value; use mime_type for evidence
    mime_type: str | None
    file_size: int | None
    caption: str | None
    filename: str | None
    duration: int | None
    dimensions: tuple[int, int] | None
    is_voice_message: bool | None


def context_projection(context: BaseMessageContext) -> ContextProjection:
    return ContextProjection(
        original_message_id=context.original_message_id,
        original_sender_id=context.original_sender_id,
        is_reply=context.is_reply,
        is_forward=context.is_forward,
    )


def message_fields(message: BaseMessage) -> dict:
    context = message.get_context() if message.has_context() else None
    return {
        "platform": message.platform.value,
        "message_type": message.message_type.value,
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "conversation_id": message.conversation_id,
        "conversation_type": message.conversation_type.value,
        "timestamp": message.timestamp,
        "processed_at": message.processed_at.isoformat(),
        "has_context": message.has_context(),
        "context": context_projection(context) if context else None,
    }


def text_projection(message: BaseTextMessage) -> dict:
    return TextProjection(
        **message_fields(message),
        content=message.text_content,
        text_length=len(message.text_content),
        is_reply=message.is_reply,
        is_forwarded=message.is_forwarded,
        is_frequently_forwarded=getattr(message, "is_frequently_forwarded", None),
    ).model_dump(mode="json")


def selection_projection(message: BaseInteractiveMessage) -> dict:
    return SelectionProjection(
        **message_fields(message),
        interactive_type=message.interactive_type.value,
        selected_option_id=message.selected_option_id,
        selected_option_title=message.selected_option_title,
        original_message_id=message.original_message_id or None,
        is_button_reply=message.is_button_reply,
        is_list_reply=message.is_list_reply,
        is_quick_reply=getattr(message, "is_quick_reply", False),
    ).model_dump(mode="json")


def media_projection(message: BaseMessage) -> dict:
    message = cast("BaseMediaMessage", message)
    return MediaProjection(
        **message_fields(message),
        media_id=message.media_id,
        media_family=message.message_type.value,
        media_type=message.media_type.value,
        mime_type=message.mime_type,
        file_size=message.file_size,
        caption=message.caption,
        filename=getattr(message, "filename", None),
        duration=getattr(message, "duration", None),
        dimensions=getattr(message, "dimensions", None),
        is_voice_message=getattr(message, "is_voice_message", None),
    ).model_dump(mode="json")


class ReactionProjection(MessageProjection):
    target_message_id: str
    emoji: str
    is_removal: bool


def reaction_projection(message: BaseReactionMessage) -> dict:
    return ReactionProjection(
        **message_fields(message),
        target_message_id=message.target_message_id,
        emoji=message.emoji,
        is_removal=message.is_removal,
    ).model_dump(mode="json")
