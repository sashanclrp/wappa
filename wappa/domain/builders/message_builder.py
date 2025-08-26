"""
Message builder pattern for creating complex messages with validation.

Provides a fluent interface for constructing messages while ensuring platform
compatibility and validation.
"""

from typing import Any, Self

from wappa.domain.factories.message_factory import MessageFactory


class MessageBuilder:
    """
    Fluent builder for creating messages with validation.

    Provides a chainable interface for constructing messages while
    ensuring platform compatibility and validation.

    Currently supports basic messaging operations. Future implementations will add:
    - Button builder for interactive button messages
    - List builder for interactive list messages
    - Template builder for template messages
    - Media builder for media messages
    """

    def __init__(self, factory: MessageFactory, recipient: str):
        """Initialize message builder.

        Args:
            factory: Message factory for creating platform-specific payloads
            recipient: Recipient identifier for the message
        """
        self._factory = factory
        self._recipient = recipient
        self._message_data: dict[str, Any] = {}
        self._message_type: str | None = None

    def text(self, content: str) -> Self:
        """Set text content for the message.

        Args:
            content: Text content of the message

        Returns:
            Self for method chaining
        """
        self._message_data["text"] = content
        self._message_type = "text"
        return self

    def reply_to(self, message_id: str) -> Self:
        """Set reply-to message ID.

        Args:
            message_id: Message ID to reply to (creates a thread)

        Returns:
            Self for method chaining
        """
        self._message_data["reply_to_message_id"] = message_id
        return self

    def disable_preview(self) -> Self:
        """Disable URL preview for links in the message.

        Returns:
            Self for method chaining
        """
        self._message_data["disable_preview"] = True
        return self

    def enable_preview(self) -> Self:
        """Enable URL preview for links in the message (default behavior).

        Returns:
            Self for method chaining
        """
        self._message_data["disable_preview"] = False
        return self

    def read_status(self, message_id: str, typing: bool = False) -> Self:
        """Set read status parameters.

        Args:
            message_id: Message ID to mark as read
            typing: Whether to show typing indicator

        Returns:
            Self for method chaining
        """
        self._message_data["message_id"] = message_id
        self._message_data["typing"] = typing
        self._message_type = "read_status"
        return self

    def build(self) -> dict[str, Any]:
        """Build the message payload.

        Creates the final message payload using the configured factory
        and validates it before returning.

        Returns:
            Platform-specific message payload

        Raises:
            ValueError: If message type is not set or required data is missing
            RuntimeError: If message validation fails
        """
        if self._message_type == "text":
            if "text" not in self._message_data:
                raise ValueError("Text content is required for text messages")

            payload = self._factory.create_text_message(
                text=self._message_data["text"],
                recipient=self._recipient,
                reply_to_message_id=self._message_data.get("reply_to_message_id"),
                disable_preview=self._message_data.get("disable_preview", False),
            )

        elif self._message_type == "read_status":
            if "message_id" not in self._message_data:
                raise ValueError("Message ID is required for read status messages")

            payload = self._factory.create_read_status_message(
                message_id=self._message_data["message_id"],
                typing=self._message_data.get("typing", False),
            )

        else:
            raise ValueError(f"Unsupported message type: {self._message_type}")

        # Validate the built payload
        if not self._factory.validate_message(payload):
            raise RuntimeError("Built message payload failed validation")

        return payload

    def validate(self) -> bool:
        """Validate the current message configuration without building.

        Returns:
            True if current configuration is valid, False otherwise
        """
        try:
            self.build()
            return True
        except (ValueError, RuntimeError):
            return False

    def get_limits(self) -> dict[str, Any]:
        """Get platform-specific message limits.

        Returns:
            Dictionary containing platform limits for validation
        """
        return self._factory.get_message_limits()


# Usage example functions for documentation
def create_text_message_example(
    factory: MessageFactory, recipient: str, text: str
) -> dict[str, Any]:
    """Example: Create a simple text message."""
    return MessageBuilder(factory, recipient).text(text).build()


def create_reply_message_example(
    factory: MessageFactory, recipient: str, text: str, reply_to: str
) -> dict[str, Any]:
    """Example: Create a reply message with URL preview disabled."""
    return (
        MessageBuilder(factory, recipient)
        .text(text)
        .reply_to(reply_to)
        .disable_preview()
        .build()
    )


def create_read_status_example(
    factory: MessageFactory, message_id: str, with_typing: bool = False
) -> dict[str, Any]:
    """Example: Create a read status message with optional typing."""
    return (
        MessageBuilder(factory, "")  # recipient not needed for read status
        .read_status(message_id, typing=with_typing)
        .build()
    )
