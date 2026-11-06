"""``WhatsAppMessenger``: the Host-facing WhatsApp Platform Messenger.

Ready on the handler as ``self.whatsapp`` for every WhatsApp dispatch (``None``
on other Platforms). It receives the dispatch's core Messenger, forwards the
whole ``IMessenger`` contract to it and adds only what WhatsApp alone has:
``templates`` (Template Messaging) and the User Data Requests
``send_location_request`` / ``send_contact_request``. Every send still runs
through the Messenger Pipeline's middleware.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wappa.core.messaging.platform_messenger import PlatformMessenger
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.interfaces.user_data_requests import IUserDataRequests
from wappa.domain.messaging_targets import DirectMessage

if TYPE_CHECKING:
    from wappa.domain.results import MessageResult


class WhatsAppMessenger(PlatformMessenger):
    """The dispatch's Messenger plus WhatsApp's Templates and User Data Requests."""

    def __init__(self, messenger: IMessenger) -> None:
        super().__init__(messenger)
        self.templates: ITemplateMessaging = messenger.require_capability(
            ITemplateMessaging
        )
        """WhatsApp Templates: ``send_text_template``, ``send_media_template``,
        ``send_location_template``."""
        self._user_data_requests: IUserDataRequests = messenger.require_capability(
            IUserDataRequests
        )

    async def send_location_request(
        self, body: str, target: DirectMessage, reply_to_message_id: str | None = None
    ) -> MessageResult:
        """Ask the User to share a location; the reply is a location message."""
        return await self._user_data_requests.send_location_request(
            body, target, reply_to_message_id
        )

    async def send_contact_request(
        self,
        body: str,
        target: DirectMessage,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        """Ask the User to share a phone number; the reply is a contact message."""
        return await self._user_data_requests.send_contact_request(
            body, target, reply_to_message_id
        )


__all__ = ["WhatsAppMessenger"]
