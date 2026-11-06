"""Instagram outbound echoes: typed content under ``OutboundEchoWebhook``."""

from __future__ import annotations

from typing import Any

from wappa.webhooks.core.webhook_interfaces.base_components import UserBase
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    EchoOrigin,
    OutboundEchoWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    SystemEventType,
    UniversalWebhook,
)
from wappa.webhooks.instagram.models import (
    InstagramEntry,
    InstagramMessage,
    InstagramMessagingEvent,
)

from ._base import InstagramProcessorBase


class EchoLaneMixin(InstagramProcessorBase):
    """Translate an echoed outbound message."""

    def _echo(
        self,
        entry: InstagramEntry,
        event: InstagramMessagingEvent,
        message: InstagramMessage,
        user: UserBase,
        meta: dict[str, Any],
    ) -> UniversalWebhook:
        """Outbound echo → ``OutboundEchoWebhook`` with typed content.

        Instagram echoes every outbound message, Wappa's own sends included,
        so ``origin`` starts ``UNKNOWN``; the Inbound Runtime proves it with
        the sent-message registry and drops Wappa's sends.
        """
        if not message.mid or message.is_deleted or message.is_unsupported:
            return self._system(
                meta,
                user,
                event,
                SystemEventType.UNSUPPORTED_EVENT,
                "Instagram echo without a deliverable message",
            )
        # Raw evidence for tuning the own-send filter (app_id, metadata, mid).
        self.logger.debug(
            "Instagram echo raw event: %s",
            event.model_dump_json(exclude_none=True, by_alias=True),
        )
        typed = self._message(entry, event, message, entry.id)
        if message.attachments:
            native_type = message.attachments[0].type
        elif message.text is not None:
            native_type = "text"
        else:
            native_type = "unknown"
        return OutboundEchoWebhook(
            **meta,
            webhook_id=f"echo:{message.mid}",
            user=user,
            message_id=message.mid,
            message_type=typed.message_type if typed is not None else None,
            native_type=native_type,
            message=typed,
            origin=EchoOrigin.UNKNOWN,
        )
