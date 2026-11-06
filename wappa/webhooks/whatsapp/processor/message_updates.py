"""Message update and echo lane: consumer edit / revoke and Coexistence echoes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from wappa.schemas.core.types import MessageType, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        InboxBase,
        MessageUpdateWebhook,
        OutboundEchoWebhook,
    )
    from wappa.webhooks.whatsapp.models.coexistence import (
        CoexistenceMessage,
        SmbMessageEchoesWebhookValue,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _MessageUpdatesMixin(_ProcessorBase):
    """Message update and echo lane: consumer edit / revoke and Coexistence echoes."""

    def _create_message_update_webhook(
        self,
        webhook: WhatsAppWebhook,
        message: BaseMessage,
        inbox_base: InboxBase,
    ) -> MessageUpdateWebhook:
        """Consumer ``edit`` / ``revoke`` → ``MessageUpdateWebhook`` (ADR-0025).

        The same lane Instagram edits and unsends use. An edit's replacement
        content is parsed with the inbound message models.
        """
        from wappa.webhooks.core.webhook_interfaces import (
            MessageUpdateKind,
            MessageUpdateWebhook,
        )
        from wappa.webhooks.whatsapp.message_types.lifecycle import (
            WhatsAppLifecycleMessage,
        )

        lifecycle = cast(WhatsAppLifecycleMessage, message)
        user = self._create_user_base_from_contacts(webhook, lifecycle.sender_id)
        common: dict[str, Any] = {
            "inbox": inbox_base,
            "user": user,
            "timestamp": datetime.fromtimestamp(lifecycle.timestamp, tz=UTC),
            "platform": PlatformType.WHATSAPP,
            "webhook_id": webhook.get_webhook_id(),
        }
        if lifecycle.revoke is not None:
            return MessageUpdateWebhook(
                **common,
                update_kind=MessageUpdateKind.DELETED,
                message_id=lifecycle.revoke.original_id,
            )
        assert lifecycle.edit is not None  # model validator guarantees one
        edit = lifecycle.edit
        replacement = self._typed_replacement(lifecycle, edit.original_id)
        text = getattr(replacement, "text_content", None)
        return MessageUpdateWebhook(
            **common,
            update_kind=MessageUpdateKind.EDITED,
            message_id=edit.original_id,
            text=text if isinstance(text, str) else None,
            message=replacement,
        )

    def _typed_replacement(
        self, lifecycle: Any, original_id: str
    ) -> BaseMessage | None:
        """Parse an edit's replacement with the inbound model of its type."""
        content = lifecycle.edit.message
        data: dict[str, Any] = {
            "id": original_id,
            "timestamp": lifecycle.timestamp_str,
            "type": content.type,
        }
        if lifecycle.from_:
            data["from"] = lifecycle.from_
        if lifecycle.from_bsuid:
            data["from_user_id"] = lifecycle.from_bsuid
        body = getattr(content, content.type, None)
        if body is None:
            return None
        data[content.type] = body
        try:
            kind = MessageType({"contacts": "contact"}.get(content.type, content.type))
            return self._create_message_from_data(data, kind)
        except Exception as exc:
            self.logger.info(
                "Edit replacement of type %r has no inbound model: %s",
                content.type,
                type(exc).__name__,
            )
            return None

    # Keys a Coexistence echo carries that inbound message models do not.
    _ECHO_ONLY_KEYS = frozenset(
        {"to", "to_user_id", "to_parent_user_id", "history_context"}
    )

    def _typed_coexistence_message(
        self, raw: CoexistenceMessage
    ) -> tuple[BaseMessage | None, MessageType | None]:
        """Parse a Coexistence message with the inbound model of its type.

        Echo- and history-only keys are dropped first. A shape with no inbound
        model (for example an interactive message the owner sent) returns
        ``(None, type)``; it is never passed on as a dict.
        """
        data = {
            k: v
            for k, v in raw.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ).items()
            if k not in self._ECHO_ONLY_KEYS
        }
        message_type: MessageType | None = None
        try:
            message_type = MessageType({"contacts": "contact"}.get(raw.type, raw.type))
            return self._create_message_from_data(data, message_type), message_type
        except Exception as exc:
            self.logger.info(
                "Coexistence message %s of type %r has no inbound model: %s",
                raw.id,
                raw.type,
                type(exc).__name__,
            )
            return None, message_type

    def _create_echo_webhook(
        self,
        webhook: WhatsAppWebhook,
        value: SmbMessageEchoesWebhookValue,
        inbox_base: InboxBase,
    ) -> OutboundEchoWebhook:
        """Coexistence ``smb_message_echoes`` → ``OutboundEchoWebhook``.

        Meta echoes only messages the owner sent from the WhatsApp Business
        app or a linked device (Cloud API sends are never echoed), so the
        origin is ``BUSINESS_APP``.
        """
        from wappa.webhooks.core.webhook_interfaces import (
            EchoOrigin,
            OutboundEchoWebhook,
        )

        echo = value.message_echoes[0]
        message, message_type = self._typed_coexistence_message(echo)
        user = self._create_user_base_from_contacts(
            webhook, echo.to_user_id or echo.to or ""
        )
        return OutboundEchoWebhook(
            inbox=inbox_base,
            user=user,
            message_id=echo.id,
            message_type=message_type,
            native_type=echo.type,
            message=message,
            origin=EchoOrigin.BUSINESS_APP,
            timestamp=datetime.fromtimestamp(int(echo.timestamp), tz=UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=f"echo:{echo.id}",
        )
