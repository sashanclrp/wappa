"""Pure Instagram translation into Universal Models; no credentials or I/O.

One routed delivery carries exactly one ``messaging`` event or one
``changes`` item. Lanes:

==========================  ===============================================
Native evidence             Universal Model / hook
==========================  ===============================================
message (text/media/share)  InboundMessageWebhook → process_message
message.quick_reply         InboundMessageWebhook (selection) → once
message.is_deleted          MessageUpdateWebhook(deleted)
message_edit                MessageUpdateWebhook(edited)
read                        StatusWebhook(READ)
postback                    InboundMessageWebhook (button selection), like
                            a WhatsApp button_reply (ADR-0025)
referral (standalone)       SystemWebhook(REFERRAL)
echo / is_self              OutboundEchoWebhook → process_outbound_echo; the
                            runtime drops Wappa's own sends (ADR-0023)
reaction / unreact          InboundMessageWebhook(REACTION), like WhatsApp
unsupported, …              SystemWebhook(UNSUPPORTED_EVENT); no automation
comments / live_comments    IncomingCommentWebhook → process_comment
mentions                    MentionWebhook → process_mention
registered extension field  CustomWebhook → registered handler
other change field          SystemWebhook(UNSUPPORTED_EVENT)
==========================  ===============================================
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from wappa.core.inbound.platform_webhooks import RoutedWebhookDelivery
from wappa.core.logging.logger import get_logger
from wappa.schemas.core.types import PlatformType
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.core.webhook_interfaces.base_components import InboxBase
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import UniversalWebhook
from wappa.webhooks.instagram.fields import INSTAGRAM_BUILTIN_FIELDS
from wappa.webhooks.instagram.models import InstagramWebhook
from wappa.webhooks.instagram.routing import route_instagram_payload

from .changes import ChangesLaneMixin
from .comments import CommentsLaneMixin
from .echo import EchoLaneMixin
from .mentions import MentionsLaneMixin
from .messages import MessagingLaneMixin

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.domain.inbox.ports import IInboxCredentialResolver


class InstagramWebhookProcessor(
    MessagingLaneMixin,
    EchoLaneMixin,
    ChangesLaneMixin,
    CommentsLaneMixin,
    MentionsLaneMixin,
):
    """Instagram ``PlatformWebhooks`` adapter: entry routing and translation."""

    builtin_fields: ClassVar[frozenset[str]] = INSTAGRAM_BUILTIN_FIELDS

    def __init__(self, field_registry: FieldHandlerRegistry | None = None) -> None:
        self.logger = get_logger(__name__)
        # ``None`` means the Host registered no extension fields.
        self._field_registry = field_registry

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    async def route(
        self, payload: dict[str, Any], resolver: IInboxCredentialResolver
    ) -> tuple[RoutedWebhookDelivery, ...]:
        return await route_instagram_payload(payload, resolver)

    async def translate(
        self, payload: dict[str, Any], *, inbox_id: str
    ) -> UniversalWebhook:
        """Translate one routed event; the Inbox is the entry's account ID.

        Every Instagram entry carries its account ID, so ``inbox_id`` (the
        routed Inbox) is checked against it by the runtime after translation.
        """
        container = InstagramWebhook.model_validate(payload)
        report_schema_drift(container, platform="instagram", logger=self.logger)
        if len(container.entry) != 1:
            raise ValueError("Instagram processor requires one routed entry")
        entry = container.entry[0]
        if len(entry.messaging) + len(entry.changes) != 1:
            raise ValueError("Instagram processor requires one routed event")
        inbox = InboxBase(
            inbox_id=entry.id, display_address=None, platform_account_id=entry.id
        )
        if entry.changes:
            return self._from_change(entry, entry.changes[0], inbox, payload)
        return self._from_messaging(entry, entry.messaging[0], inbox, payload)
