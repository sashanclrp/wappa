"""Platform-agnostic contact and location sharing message base classes."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from wappa.schemas.core.types import (
    MessageType,
)
from wappa.webhooks.core.base_message.core import BaseMessage


class BaseContactMessage(BaseMessage):
    """Platform-agnostic contact sharing message base class."""

    @property
    def message_type(self) -> MessageType:
        """Contact messages always have CONTACT type."""
        return MessageType.CONTACT

    @property
    @abstractmethod
    def contact_name(self) -> str:
        """Get the shared contact's name."""
        pass

    @property
    @abstractmethod
    def contact_phone(self) -> str | None:
        """Get the shared contact's phone number if available."""
        pass

    @property
    @abstractmethod
    def contact_data(self) -> dict[str, Any]:
        """Get all available contact information."""
        pass


class BaseLocationMessage(BaseMessage):
    """Platform-agnostic location sharing message base class."""

    @property
    def message_type(self) -> MessageType:
        """Location messages always have LOCATION type."""
        return MessageType.LOCATION

    @property
    @abstractmethod
    def latitude(self) -> float:
        """Get the latitude coordinate."""
        pass

    @property
    @abstractmethod
    def longitude(self) -> float:
        """Get the longitude coordinate."""
        pass

    @property
    @abstractmethod
    def address(self) -> str | None:
        """Get the address description if available."""
        pass

    @property
    @abstractmethod
    def location_name(self) -> str | None:
        """Get the location name if available."""
        pass
