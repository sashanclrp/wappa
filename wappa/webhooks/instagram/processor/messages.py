"""Instagram ``messaging`` events: reads, edits, postbacks, referrals, reactions, messages."""

from __future__ import annotations

from typing import Any

from wappa.schemas.core.types import MessageStatus
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
    SystemEventDetail,
    UserBase,
)
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    MessageUpdateKind,
    MessageUpdateWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    InboundMessageWebhook,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
    UniversalWebhook,
)
from wappa.webhooks.instagram.message_types import (
    ATTACHMENT_CLASSES,
    InstagramButtonReplyMessage,
    InstagramQuickReplyMessage,
    InstagramReactionMessage,
    InstagramTextMessage,
)
from wappa.webhooks.instagram.models import (
    InstagramEntry,
    InstagramMessage,
    InstagramMessagingEvent,
    is_echo,
)

from ._base import InstagramProcessorBase
from .context import entry_referral, message_context, native_timestamp


class MessagingLaneMixin(InstagramProcessorBase):
    """Translate one ``entry.messaging[]`` event."""

    def _from_messaging(
        self,
        entry: InstagramEntry,
        event: InstagramMessagingEvent,
        inbox: InboxBase,
        payload: dict[str, Any],
    ) -> UniversalWebhook:
        echo = is_echo(event, entry.id)
        user_id = event.recipient.id if echo else event.sender.id
        user = UserBase(platform_user_id=user_id)
        meta: dict[str, Any] = {
            "inbox": inbox,
            "timestamp": native_timestamp(event.timestamp),
            "platform": self.platform,
            "raw_webhook_data": payload,
        }

        if event.read is not None:
            return StatusWebhook(
                **meta,
                webhook_id=f"read:{event.read.mid}:{event.timestamp}",
                message_id=event.read.mid,
                status=MessageStatus.READ,
                user=user,
                user_id=user_id,
                recipient_platform_id=user_id,
            )
        if event.message_edit is not None:
            edit = event.message_edit
            return MessageUpdateWebhook(
                **meta,
                webhook_id=f"edit:{edit.mid}:{edit.num_edit or event.timestamp}",
                user=user,
                update_kind=MessageUpdateKind.EDITED,
                message_id=edit.mid,
                text=edit.text,
                edit_count=edit.num_edit,
            )
        if event.postback is not None:
            postback = event.postback
            if not postback.payload:
                return self._system(
                    meta,
                    user,
                    event,
                    SystemEventType.UNSUPPORTED_EVENT,
                    "Instagram postback without a payload (ignored)",
                )
            mid = postback.mid or f"postback:{event.timestamp}"
            return InboundMessageWebhook(
                **meta,
                webhook_id=mid,
                user=user,
                message=InstagramButtonReplyMessage(
                    id=mid,
                    sender=user_id,
                    account_id=entry.id,
                    timestamp_ms=event.timestamp,
                    title=postback.title or "",
                    payload=postback.payload,
                ),
                entry_referral=entry_referral(postback.referral),
            )
        if event.referral is not None:
            return SystemWebhook(
                **meta,
                webhook_id=f"referral:{event.timestamp}",
                user=user,
                system_event_type=SystemEventType.REFERRAL,
                event_detail=SystemEventDetail(
                    entry_referral=entry_referral(event.referral),
                    detail="Instagram standalone entry-point referral",
                ),
            )
        if event.reaction is not None:
            reaction = event.reaction
            reaction_id = f"reaction:{reaction.mid}:{event.timestamp}"
            return InboundMessageWebhook(
                **meta,
                webhook_id=reaction_id,
                user=user,
                message=InstagramReactionMessage(
                    id=reaction_id,
                    sender=user_id,
                    account_id=entry.id,
                    timestamp_ms=event.timestamp,
                    target_mid=reaction.mid,
                    action=reaction.action,
                    reaction_name=reaction.reaction,
                    emoji_value=reaction.emoji,
                ),
            )
        message = event.message
        if message is None:
            return self._system(
                meta,
                user,
                event,
                SystemEventType.UNSUPPORTED_EVENT,
                "Instagram messaging event kind not implemented",
            )
        if echo:
            return self._echo(entry, event, message, user, meta)
        if message.is_deleted and message.mid:
            return MessageUpdateWebhook(
                **meta,
                webhook_id=f"delete:{message.mid}",
                user=user,
                update_kind=MessageUpdateKind.DELETED,
                message_id=message.mid,
            )
        normalized = self._message(entry, event, message, user_id)
        if normalized is None:
            return self._system(
                meta,
                user,
                event,
                SystemEventType.UNSUPPORTED_EVENT,
                "Instagram message content not implemented (no automation)",
            )
        return InboundMessageWebhook(
            **meta,
            webhook_id=message.mid or f"message:{event.timestamp}",
            user=user,
            message=normalized,
            entry_referral=entry_referral(message.referral),
        )

    def _message(
        self,
        entry: InstagramEntry,
        event: InstagramMessagingEvent,
        message: InstagramMessage,
        user_id: str,
    ) -> BaseMessage | None:
        if not message.mid or message.is_unsupported:
            return None
        common: dict[str, Any] = {
            "id": message.mid,
            "sender": user_id,
            "account_id": entry.id,
            "timestamp_ms": event.timestamp,
            "context": message_context(message),
        }
        if message.quick_reply is not None:
            return InstagramQuickReplyMessage(
                **common,
                text=message.text or "",
                payload=message.quick_reply.payload,
            )
        if message.attachments:
            kind = ATTACHMENT_CLASSES.get(message.attachments[0].type)
            if kind is None:
                return None
            return kind(
                **common, attachments=tuple(message.attachments), text=message.text
            )
        if message.text is not None:
            return InstagramTextMessage(**common, text=message.text)
        return None
