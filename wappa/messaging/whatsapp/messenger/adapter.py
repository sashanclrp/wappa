"""``WhatsAppMessengerAdapter``: the composed WhatsApp ``IMessenger``."""

from __future__ import annotations

from wappa.core.logging.logger import get_logger
from wappa.domain.interfaces.media_library import IMediaLibrary
from wappa.domain.interfaces.messaging_interface import IMessenger
from wappa.domain.interfaces.template_messaging import ITemplateMessaging
from wappa.domain.interfaces.user_data_requests import IUserDataRequests
from wappa.messaging.whatsapp.client import WhatsAppClient
from wappa.messaging.whatsapp.media.library import WhatsAppMediaLibrary
from wappa.messaging.whatsapp.media.transport import WhatsAppMediaTransport
from wappa.messaging.whatsapp.messenger.interactive import _InteractiveMixin
from wappa.messaging.whatsapp.messenger.media import _MediaMixin
from wappa.messaging.whatsapp.messenger.profile import _ProfileMixin
from wappa.messaging.whatsapp.messenger.receipts import _ReceiptsMixin
from wappa.messaging.whatsapp.messenger.specialized import _SpecializedMixin
from wappa.messaging.whatsapp.messenger.templates import _TemplatesMixin
from wappa.messaging.whatsapp.messenger.text import _TextMixin
from wappa.messaging.whatsapp.payloads.media import WhatsAppMediaPayloadBuilder
from wappa.messaging.whatsapp.payloads.text import WhatsAppMessagePayloadBuilder
from wappa.schemas.core.types import PlatformType


class WhatsAppMessengerAdapter(
    _TextMixin,
    _MediaMixin,
    _InteractiveMixin,
    _SpecializedMixin,
    _TemplatesMixin,
    _ReceiptsMixin,
    _ProfileMixin,
    IMessenger,
    ITemplateMessaging,
    IUserDataRequests,
):
    def __init__(
        self,
        client: WhatsAppClient,
        media_transport: WhatsAppMediaTransport,
        inbox_id: str,
    ):
        self.client = client
        self.media_transport = media_transport
        self._inbox_id = inbox_id
        self._message_payloads = WhatsAppMessagePayloadBuilder()
        self._media_payloads = WhatsAppMediaPayloadBuilder()
        self.logger = get_logger(__name__)
        # Focused capabilities: Templates and user-data requests (WhatsApp-only)
        # and the Media Library.
        self._capabilities = {
            ITemplateMessaging: self,
            IUserDataRequests: self,
            IMediaLibrary: WhatsAppMediaLibrary(self.media_transport, self._inbox_id),
        }

    @property
    def supported_operations(self) -> frozenset[str]:
        return frozenset(
            [
                "send_text",
                "mark_as_read",
                "send_image",
                "send_video",
                "send_audio",
                "send_document",
                "send_sticker",
                "send_button_message",
                "send_list_message",
                "send_cta_message",
                "send_carousel",
                "send_contact",
                "send_location",
                "resolve_platform_user_profile",
            ]
        )

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    @property
    def inbox_id(self) -> str:
        return self._inbox_id
