"""Redis PubSub interface for real-time notifications."""

from abc import ABC, abstractmethod
from typing import Any, Literal

PubSubEventType = Literal[
    "incoming_message",  # User → WhatsApp → Wappa (webhook)
    "outgoing_message",  # API route → WhatsApp (via REST API)
    "bot_reply",  # process_message() → self.messenger → WhatsApp
    "status_change",  # WhatsApp delivery/read receipts
]


class IPubSubPublisher(ABC):
    """
    Interface for publishing notifications via Redis PubSub.

    Context (tenant_id, user_id, platform) is established via constructor.
    Notifications are lightweight signals - actual data should be stored in
    UserCache and fetched by subscribers based on the notification.

    Event Types:
        incoming_message: Message received from user via webhook
        outgoing_message: Message sent via API routes (POST /api/messages/*)
        bot_reply: Message sent by bot via self.messenger in process_message()
        status_change: Delivery/read status updates from WhatsApp
    """

    @abstractmethod
    async def publish(
        self,
        event_type: PubSubEventType,
        data: dict[str, Any],
    ) -> int:
        """
        Publish notification to channel.

        Args:
            event_type: Type of event
            data: Event-specific data (kept lightweight - just identifiers)

        Returns:
            Number of subscribers that received the message
        """
        ...

    @abstractmethod
    def get_channel(self, event_type: PubSubEventType) -> str:
        """Get channel name for event type."""
        ...
