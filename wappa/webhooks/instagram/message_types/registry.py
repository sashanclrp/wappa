"""Implemented inbound attachment types mapped to their message classes."""

from __future__ import annotations

from ._attachment import InstagramAttachmentMessage
from .audio import InstagramAudioMessage
from .file import InstagramFileMessage
from .image import InstagramImageMessage
from .share import InstagramShareMessage
from .video import InstagramVideoMessage

ATTACHMENT_CLASSES: dict[str, type[InstagramAttachmentMessage]] = {
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
