"""Platform-agnostic reaction message base class."""

from __future__ import annotations

from abc import abstractmethod

from wappa.schemas.core.types import (
    MessageType,
)
from wappa.webhooks.core.base_message.core import BaseMessage


class BaseReactionMessage(BaseMessage):
    """A User reacted to an earlier message, or removed a reaction (ADR-0025).

    One inbound shape on every Platform: WhatsApp ``reaction`` messages and
    Instagram ``message_reactions`` both arrive as ``InboundMessageWebhook``
    with this message type.
    """

    @property
    def message_type(self) -> MessageType:
        return MessageType.REACTION

    @property
    @abstractmethod
    def target_message_id(self) -> str:
        """Native ID of the message the reaction applies to."""

    @property
    @abstractmethod
    def emoji(self) -> str:
        """The reaction emoji; an empty string when the reaction was removed."""

    @property
    @abstractmethod
    def is_removal(self) -> bool:
        """``True`` when the User removed an earlier reaction."""
