"""Platform-agnostic text message base class."""

from __future__ import annotations

from abc import abstractmethod

from wappa.schemas.core.types import (
    MessageType,
)
from wappa.webhooks.core.base_message.core import BaseMessage


class BaseTextMessage(BaseMessage):
    """
    Platform-agnostic text message base class.

    Handles text content with universal methods for common operations.
    """

    @property
    def message_type(self) -> MessageType:
        """Text messages always have TEXT type."""
        return MessageType.TEXT

    @property
    @abstractmethod
    def text_content(self) -> str:
        """Get the text content of the message."""
        pass

    @property
    @abstractmethod
    def is_reply(self) -> bool:
        """Check if this is a reply to another message."""
        pass

    @property
    @abstractmethod
    def is_forwarded(self) -> bool:
        """Check if this message was forwarded."""
        pass

    @property
    def is_frequently_forwarded(self) -> bool:
        """Check if this message was forwarded many times."""
        return False  # Default implementation

    @abstractmethod
    def get_reply_context(self) -> tuple[str | None, str | None]:
        """
        Get reply context information.

        Returns:
            Tuple of (original_sender_id, original_message_id) if reply,
            (None, None) otherwise.
        """
        pass

    def get_text_length(self) -> int:
        """Get the length of the text content."""
        return len(self.text_content)

    def contains_keyword(self, keyword: str, case_sensitive: bool = False) -> bool:
        """Check if text content contains a specific keyword."""
        text = self.text_content
        search_text = text if case_sensitive else text.lower()
        search_keyword = keyword if case_sensitive else keyword.lower()
        return search_keyword in search_text

    def contains_any_keyword(
        self, keywords: list[str], case_sensitive: bool = False
    ) -> bool:
        """Check if text content contains any of the specified keywords."""
        return any(self.contains_keyword(kw, case_sensitive) for kw in keywords)
