"""Requests for the User's own data as a focused capability (ADR-0025 rule 4).

A location request and a contact (phone number) request open a native
Platform flow that returns the User's location or phone number as a webhook.
WhatsApp has both; a text prompt elsewhere would not return the data, so they
are not ``IMessenger`` methods. Reach them with
``messenger.require_capability(IUserDataRequests)``; HTTP routes gate on
``requires_capability(IUserDataRequests)`` (501 elsewhere). Through a
``MessengerPipeline`` the capability still runs the message middleware chain
under the method names ``send_location_request`` / ``send_contact_request``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from wappa.domain.messaging_targets import DirectMessage

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult


class IUserDataRequests(ABC):
    """Ask the User to share a location or phone number, bound to one Inbox."""

    @abstractmethod
    async def send_location_request(
        self, body: str, target: DirectMessage, reply_to_message_id: str | None = None
    ) -> MessageResult:
        """Ask the User to share a location; the reply is a location message."""

    @abstractmethod
    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Ask the User to share a phone number; the reply is a contact message."""


USER_DATA_REQUEST_METHODS = frozenset({"send_location_request", "send_contact_request"})

__all__ = ["USER_DATA_REQUEST_METHODS", "IUserDataRequests"]
