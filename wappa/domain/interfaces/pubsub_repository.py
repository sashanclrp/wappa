"""
Pub/Sub repository interface.

Defines contract for Redis pub/sub messaging in Redis.
"""

from abc import abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

from .base_repository import IBaseRepository


class IPubSubRepository(IBaseRepository):
    """
    Interface for Redis pub/sub messaging.

    Handles real-time messaging and event broadcasting with context binding.
    Uses the 'pubsub' Redis pool (database 5).
    """

    @abstractmethod
    async def publish_message(
        self, channel: str, message: dict[str, Any], user_id: str | None = None
    ) -> int:
        """
        Publish message to channel.

        Args:
            channel: Channel name
            message: Message data
            user_id: Optional user context for filtering

        Returns:
            Number of subscribers that received the message
        """
        pass

    @abstractmethod
    async def subscribe_to_channel(
        self, channel: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to channel with callback.

        Args:
            channel: Channel name
            callback: Function to call when message received
        """
        pass

    @abstractmethod
    async def unsubscribe_from_channel(self, channel: str) -> None:
        """
        Unsubscribe from channel.

        Args:
            channel: Channel name
        """
        pass

    @abstractmethod
    async def subscribe_to_pattern(
        self, pattern: str, callback: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to channel pattern with callback.

        Args:
            pattern: Channel pattern (e.g., 'user:*:events')
            callback: Function to call with (channel, message) when message received
        """
        pass

    @abstractmethod
    async def unsubscribe_from_pattern(self, pattern: str) -> None:
        """
        Unsubscribe from channel pattern.

        Args:
            pattern: Channel pattern
        """
        pass

    @abstractmethod
    async def get_channel_subscribers(self, channel: str) -> int:
        """
        Get number of subscribers for channel.

        Args:
            channel: Channel name

        Returns:
            Number of subscribers
        """
        pass

    @abstractmethod
    async def get_active_channels(self) -> list[str]:
        """
        Get list of active channels.

        Returns:
            List of channel names with active subscribers
        """
        pass

    @abstractmethod
    async def publish_user_event(
        self, user_id: str, event_type: str, event_data: dict[str, Any]
    ) -> int:
        """
        Publish user-specific event.

        Args:
            user_id: User identifier
            event_type: Type of event
            event_data: Event data

        Returns:
            Number of subscribers that received the event
        """
        pass

    @abstractmethod
    async def subscribe_to_user_events(
        self, user_id: str, callback: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """
        Subscribe to all events for specific user.

        Args:
            user_id: User identifier
            callback: Function to call with (event_type, event_data)
        """
        pass

    @abstractmethod
    async def listen_for_messages(
        self, channels: list[str]
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Listen for messages on multiple channels.

        Args:
            channels: List of channel names

        Yields:
            Message data as it arrives
        """
        pass
