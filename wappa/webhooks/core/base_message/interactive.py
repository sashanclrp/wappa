"""Platform-agnostic interactive message base class."""

from __future__ import annotations

from abc import abstractmethod

from wappa.schemas.core.types import (
    InteractiveType,
    MessageType,
)
from wappa.webhooks.core.base_message.core import BaseMessage


class BaseInteractiveMessage(BaseMessage):
    """
    Platform-agnostic interactive message base class.

    Handles button clicks, list selections, and other interactive elements.
    """

    @property
    def message_type(self) -> MessageType:
        """Interactive messages always have INTERACTIVE type."""
        return MessageType.INTERACTIVE

    @property
    @abstractmethod
    def interactive_type(self) -> InteractiveType:
        """Get the type of interactive element (button, list, etc.)."""
        pass

    @property
    @abstractmethod
    def selected_option_id(self) -> str:
        """Get the ID of the selected option."""
        pass

    @property
    @abstractmethod
    def selected_option_title(self) -> str:
        """Get the title/text of the selected option."""
        pass

    @property
    @abstractmethod
    def original_message_id(self) -> str | None:
        """Get the ID of the original interactive message."""
        pass

    @property
    @abstractmethod
    def is_button_reply(self) -> bool:
        """Check if this is a button selection."""
        pass

    @property
    @abstractmethod
    def is_list_reply(self) -> bool:
        """Check if this is a list selection."""
        pass

    def matches_option_pattern(self, pattern: str) -> bool:
        """Check if selected option ID matches a pattern (e.g., starts with prefix)."""
        return self.selected_option_id.startswith(pattern)

    def get_option_category(self, delimiter: str = "_") -> str | None:
        """Extract option category from ID using delimiter."""
        parts = self.selected_option_id.split(delimiter)
        return parts[0] if len(parts) > 1 else None
