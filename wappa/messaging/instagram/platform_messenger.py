"""``InstagramMessenger``: the Host-facing Instagram Platform Messenger.

Ready on the handler as ``self.instagram`` for every Instagram dispatch
(``None`` on other Platforms). It receives the dispatch's core Messenger,
forwards the whole ``IMessenger`` contract to it and adds only what Instagram
alone has: ``comments`` (Comment Controls: public replies, hide, unhide,
delete, enable or disable comments), ``content`` (post and comment reads) and
``history`` (conversation history reads).
"""

from __future__ import annotations

from functools import cached_property
from typing import cast

from wappa.core.messaging.platform_messenger import PlatformMessenger
from wappa.domain.interfaces.conversation_capabilities import (
    ICommentControls,
    IConversationContentReader,
)
from wappa.domain.interfaces.history_reader import IConversationHistoryReader
from wappa.messaging.instagram.capabilities.content import InstagramContentReader


class InstagramMessenger(PlatformMessenger):
    """The dispatch's Messenger plus Instagram's comments and conversation reads."""

    # Each capability is looked up on first use, so binding a handler to a
    # Messenger (a test fake, say) never requires capabilities the code does
    # not touch.

    @cached_property
    def comments(self) -> ICommentControls:
        """Comment Controls: ``reply_comment``, ``hide_comment``,
        ``unhide_comment``, ``delete_comment``, ``set_comments_enabled``."""
        return self.messenger.require_capability(ICommentControls)

    @cached_property
    def content(self) -> InstagramContentReader:
        """Post and comment reads: ``get_post``, ``get_comment``,
        ``list_comments``, ``list_replies``, and the mention reads
        ``get_mentioned_post`` / ``get_mentioned_comment``."""
        reader = self.messenger.require_capability(IConversationContentReader)
        # Scheduled scopes may return a deferred wrapper with the same async
        # surface, so discovery must not require the concrete reader instance.
        return cast(InstagramContentReader, reader)

    @cached_property
    def history(self) -> IConversationHistoryReader:
        """Conversation history reads: ``read_history``."""
        return self.messenger.require_capability(IConversationHistoryReader)


__all__ = ["InstagramMessenger"]
