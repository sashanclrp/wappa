"""Instagram ``BaseMessage`` subclasses, one module per message family."""

from __future__ import annotations

from .audio import InstagramAudioMessage
from .context import InstagramMessageContext
from .file import InstagramFileMessage
from .image import InstagramImageMessage
from .reaction import InstagramReactionMessage
from .registry import ATTACHMENT_CLASSES
from .selection import InstagramButtonReplyMessage, InstagramQuickReplyMessage
from .share import InstagramShareMessage
from .text import InstagramTextMessage
from .video import InstagramVideoMessage

__all__ = [
    "ATTACHMENT_CLASSES",
    "InstagramAudioMessage",
    "InstagramButtonReplyMessage",
    "InstagramFileMessage",
    "InstagramImageMessage",
    "InstagramMessageContext",
    "InstagramQuickReplyMessage",
    "InstagramReactionMessage",
    "InstagramShareMessage",
    "InstagramTextMessage",
    "InstagramVideoMessage",
]
