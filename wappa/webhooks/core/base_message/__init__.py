"""
Base message abstractions for platform-agnostic message handling.

This package defines the abstract base classes for different message types
that provide consistent interfaces regardless of the messaging platform.
"""

from wappa.webhooks.core.base_message.contact_location import (
    BaseContactMessage,
    BaseLocationMessage,
)
from wappa.webhooks.core.base_message.core import (
    BaseMessage,
    BaseMessageContext,
)
from wappa.webhooks.core.base_message.interactive import (
    BaseInteractiveMessage,
)
from wappa.webhooks.core.base_message.media import (
    BaseAudioMessage,
    BaseDocumentMessage,
    BaseImageMessage,
    BaseMediaMessage,
    BaseVideoMessage,
)
from wappa.webhooks.core.base_message.reaction import (
    BaseReactionMessage,
)
from wappa.webhooks.core.base_message.text import (
    BaseTextMessage,
)

__all__ = [
    "BaseAudioMessage",
    "BaseContactMessage",
    "BaseDocumentMessage",
    "BaseImageMessage",
    "BaseInteractiveMessage",
    "BaseLocationMessage",
    "BaseMediaMessage",
    "BaseMessage",
    "BaseMessageContext",
    "BaseReactionMessage",
    "BaseTextMessage",
    "BaseVideoMessage",
]
