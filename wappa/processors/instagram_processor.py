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
                            a WhatsApp button_reply (ADR-0016)
referral (standalone)       SystemWebhook(REFERRAL)
echo / is_self              OutboundEchoWebhook → process_outbound_echo; the
                            runtime drops Wappa's own sends (ADR-0018)
reaction / unreact          InboundMessageWebhook(REACTION), like WhatsApp
unsupported, …              SystemWebhook(UNSUPPORTED_EVENT); no automation
comments / live_comments    IncomingCommentWebhook → process_comment
mentions                    MentionWebhook → process_mention
registered extension field  CustomWebhook → registered handler
other change field          SystemWebhook(UNSUPPORTED_EVENT)
==========================  ===============================================
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from wappa.core.inbound.instagram_routing import route_instagram_payload
from wappa.core.inbound.platform_webhooks import RoutedWebhookDelivery
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import CommentRef, PostRef
from wappa.schemas.core.types import MessageStatus, PlatformType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.schema_drift import report_schema_drift
from wappa.webhooks.core.webhook_interfaces.base_components import (
    InboxBase,
    SystemEventDetail,
    UserBase,
)
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    CommentAuthor,
    CommentSource,
    EchoOrigin,
    EntryPointKind,
    EntryReferral,
    IncomingCommentWebhook,
    MentionSubject,
    MentionWebhook,
    MessageUpdateKind,
    MessageUpdateWebhook,
    OutboundEchoWebhook,
)
from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
    CustomWebhook,
    InboundMessageWebhook,
    StatusWebhook,
    SystemEventType,
    SystemWebhook,
    UniversalWebhook,
)
from wappa.webhooks.instagram.models import (
    ATTACHMENT_CLASSES,
    INSTAGRAM_BUILTIN_FIELDS,
    InstagramButtonReplyMessage,
    InstagramChange,
    InstagramCommentValue,
    InstagramEntry,
    InstagramMentionValue,
    InstagramMessage,
    InstagramMessageContext,
    InstagramMessagingEvent,
    InstagramQuickReplyMessage,
    InstagramReactionMessage,
    InstagramReferral,
    InstagramTextMessage,
    InstagramWebhook,
    is_echo,
)

if TYPE_CHECKING:
    from wappa.core.events.field_registry import FieldHandlerRegistry
    from wappa.domain.inbox.ports import IInboxCredentialResolver


def _timestamp(value: int | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    # Messaging uses milliseconds; change entries commonly use seconds.
    seconds = value / 1000 if value > 10**11 else value
    return datetime.fromtimestamp(seconds, tz=UTC)


def _referral(native: InstagramReferral | None) -> EntryReferral | None:
    if native is None:
        return None
    ads = native.ads_context_data
    source = (native.source or "").upper()
    if native.ad_id or source == "ADS":
        kind = EntryPointKind.AD
    elif native.ref is not None or source in {"SHORTLINK", "IGME", "LINK"}:
        kind = EntryPointKind.LINK
    else:
        kind = EntryPointKind.OTHER
    return EntryReferral(
        kind=kind,
        source=native.source,
        ref=native.ref,
        ad_id=native.ad_id,
        post_id=ads.post_id if ads else None,
        product_id=ads.product_id if ads else None,
        headline=ads.ad_title if ads else None,
        image_url=ads.photo_url if ads else None,
        video_url=ads.video_url if ads else None,
    )


class InstagramWebhookProcessor:
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
        self, payload: dict[str, Any], *, inbox_id: str | None = None
    ) -> UniversalWebhook:
        """Translate one routed event; the Inbox is the entry's account ID."""
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

    # ── messaging ───────────────────────────────────────────────────────

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
            "timestamp": _timestamp(event.timestamp),
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
                entry_referral=_referral(postback.referral),
            )
        if event.referral is not None:
            return SystemWebhook(
                **meta,
                webhook_id=f"referral:{event.timestamp}",
                user=user,
                system_event_type=SystemEventType.REFERRAL,
                event_detail=SystemEventDetail(
                    entry_referral=_referral(event.referral),
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
            entry_referral=_referral(message.referral),
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
            "context": self._context(message),
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

    @staticmethod
    def _context(message: InstagramMessage) -> InstagramMessageContext | None:
        reply = message.reply_to
        if reply is None:
            return None
        story = reply.story
        return InstagramMessageContext(
            reply_to_message_id=reply.mid,
            story_id=story.id if story else None,
            story_url=story.url if story else None,
        )

    def _system(
        self,
        meta: dict[str, Any],
        user: UserBase | None,
        event: InstagramMessagingEvent | InstagramChange,
        kind: SystemEventType,
        detail: str,
    ) -> SystemWebhook:
        raw = event.model_dump(mode="json", exclude_none=True, by_alias=True)
        if isinstance(event, InstagramMessagingEvent):
            mid = event.message.mid if event.message else None
            webhook_id = f"{kind.value}:{mid or 'event'}:{event.timestamp}"
        else:
            webhook_id = f"{kind.value}:{event.field}:{meta['timestamp'].timestamp()}"
        return SystemWebhook(
            **meta,
            webhook_id=webhook_id,
            user=user,
            system_event_type=kind,
            event_detail=SystemEventDetail(platform_event=raw, detail=detail),
        )

    # ── changes ─────────────────────────────────────────────────────────

    def _from_change(
        self,
        entry: InstagramEntry,
        change: InstagramChange,
        inbox: InboxBase,
        payload: dict[str, Any],
    ) -> UniversalWebhook:
        ref = InboxRef(platform=PlatformType.INSTAGRAM, inbox_id=entry.id)
        meta: dict[str, Any] = {
            "inbox": inbox,
            "timestamp": _timestamp(entry.time),
            "platform": self.platform,
            "raw_webhook_data": payload,
        }
        if change.field in ("comments", "live_comments"):
            value = InstagramCommentValue.model_validate(change.value)
            report_schema_drift(value, platform="instagram", logger=self.logger)
            comment_id = value.native_comment_id
            author = value.from_
            media = value.media
            return IncomingCommentWebhook(
                **meta,
                webhook_id=f"{change.field}:{comment_id}",
                comment_ref=CommentRef(inbox_ref=ref, comment_id=comment_id),
                post_ref=PostRef(inbox_ref=ref, media_id=media.id)
                if media and media.id
                else None,
                source=CommentSource(change.field),
                media_product_type=media.media_product_type if media else None,
                parent_comment_ref=CommentRef(inbox_ref=ref, comment_id=value.parent_id)
                if value.parent_id
                else None,
                author=CommentAuthor(
                    author_id=author.id,
                    username=author.username,
                    self_scoped_id=author.self_ig_scoped_id,
                )
                if author
                else None,
                text=value.text,
                ad_id=media.ad_id if media else None,
                ad_title=media.ad_title if media else None,
            )
        if change.field == "mentions":
            mention = InstagramMentionValue.model_validate(change.value)
            report_schema_drift(mention, platform="instagram", logger=self.logger)
            return MentionWebhook(
                **meta,
                webhook_id=f"mention:{mention.media_id}:{mention.comment_id or '-'}",
                subject=MentionSubject.COMMENT
                if mention.comment_id
                else MentionSubject.MEDIA,
                post_ref=PostRef(inbox_ref=ref, media_id=mention.media_id),
                comment_ref=CommentRef(inbox_ref=ref, comment_id=mention.comment_id)
                if mention.comment_id
                else None,
            )
        spec = (
            self._field_registry.get(change.field, PlatformType.INSTAGRAM)
            if self._field_registry
            else None
        )
        if spec is not None:
            return CustomWebhook(
                **meta,
                webhook_id=f"{change.field}:{entry.time or 'event'}",
                field_name=change.field,
                parsed=spec.parser(change.value),
                raw_value=change.value,
            )
        return self._system(
            meta,
            None,
            change,
            SystemEventType.UNSUPPORTED_EVENT,
            f"Instagram change field '{change.field}' is not implemented",
        )
