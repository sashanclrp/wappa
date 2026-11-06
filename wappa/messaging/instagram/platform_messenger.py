"""``InstagramMessenger``: the Host-facing Instagram Platform Messenger.

Ready on the handler as ``self.instagram`` for every Instagram dispatch
(``None`` on other Platforms). It receives the dispatch's core Messenger,
forwards the whole ``IMessenger`` contract to it and adds only what Instagram
alone has: ``comments`` (Comment Controls: public replies, hide, unhide,
delete, enable or disable comments), ``content`` (post and comment reads) and
``history`` (conversation history reads).
"""

from __future__ import annotations

from wappa.core.messaging.platform_messenger import PlatformMessenger
from wappa.domain.interfaces.conversation_capabilities import (
    ICommentControls,
    IConversationContentReader,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.domain.interfaces.messaging_interface import IMessenger


class InstagramMessenger(PlatformMessenger):
    """The dispatch's Messenger plus Instagram's comments and conversation reads."""

    def __init__(self, messenger: IMessenger) -> None:
        super().__init__(messenger)
        self.comments: ICommentControls = messenger.require_capability(ICommentControls)
        """Comment Controls: ``reply_comment``, ``hide_comment``,
        ``unhide_comment``, ``delete_comment``, ``set_comments_enabled``."""
        self.content: IConversationContentReader = messenger.require_capability(
            IConversationContentReader
        )
        """Post and comment reads: ``get_post``, ``get_comment``,
        ``list_comments``, ``list_replies``."""
        self.history: IConversationHistoryReader = messenger.require_capability(
            IConversationHistoryReader
        )
        """Conversation history reads: ``read_history``."""


__all__ = ["InstagramMessenger"]
