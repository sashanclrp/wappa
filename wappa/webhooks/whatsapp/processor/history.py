"""History lane: Coexistence history sync and Inbox connection changes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wappa.core.inbound.errors import ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType
from wappa.webhooks.whatsapp.processor._base import _ProcessorBase

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import (
        HistoryMessage,
        HistorySyncWebhook,
        InboxBase,
        InboxConnectionWebhook,
    )
    from wappa.webhooks.whatsapp.models.coexistence import (
        CoexistenceMessage,
        HistoryWebhookValue,
    )
    from wappa.webhooks.whatsapp.models.webhook import WhatsAppWebhook
    from wappa.webhooks.whatsapp.processor._base import _ProcessorBase


class _HistoryMixin(_ProcessorBase):
    """History lane: Coexistence history sync and Inbox connection changes."""

    def _history_message(
        self,
        raw: CoexistenceMessage,
        *,
        outbound: bool | None = None,
        user_ids: frozenset[str] = frozenset(),
    ) -> HistoryMessage:
        from wappa.webhooks.core.webhook_interfaces import (
            HistoryDirection,
            HistoryMessage,
        )

        # A message is inbound when the thread's User sent it.
        is_outbound = (
            outbound
            if outbound is not None
            else not ({raw.from_user_id, raw.from_} & user_ids)
        )
        message, message_type = self._typed_coexistence_message(raw)
        return HistoryMessage(
            message_id=raw.id,
            direction=HistoryDirection.OUTBOUND
            if is_outbound
            else HistoryDirection.INBOUND,
            timestamp=datetime.fromtimestamp(int(raw.timestamp), tz=UTC),
            native_type=raw.type,
            message_type=message_type,
            message=message,
            status=raw.history_context.status if raw.history_context else None,
        )

    def _create_history_webhook(
        self,
        webhook: WhatsAppWebhook,
        value: HistoryWebhookValue,
        inbox_base: InboxBase,
    ) -> HistorySyncWebhook:
        """Coexistence ``history`` → ``HistorySyncWebhook`` (typed threads).

        Covers both shapes Meta sends on this field: ``history`` chunks of
        threads, and the media-sync form with top-level ``messages`` /
        ``message_echoes`` for one contact.
        """
        from wappa.webhooks.core.webhook_interfaces import (
            HistorySyncWebhook,
            HistoryThread,
            UserBase,
        )

        threads: list[HistoryThread] = []
        phase = chunk_order = progress = None
        for chunk in value.history or []:
            meta = chunk.metadata
            phase = int(meta.phase) if str(meta.phase).isdigit() else None
            chunk_order, progress = meta.chunk_order, meta.progress
            for thread in chunk.threads:
                ctx = thread.context
                threads.append(
                    HistoryThread(
                        user=UserBase(
                            phone_number=ctx.wa_id or "",
                            bsuid=ctx.user_id,
                            parent_bsuid=ctx.parent_user_id,
                            username=ctx.username,
                        ),
                        messages=tuple(
                            self._history_message(
                                m,
                                user_ids=frozenset(
                                    i for i in (ctx.user_id, ctx.wa_id) if i
                                ),
                            )
                            for m in thread.messages
                        ),
                    )
                )
        if value.messages or value.message_echoes:
            contact = value.contacts[0] if value.contacts else None
            identity = (contact.user_id or contact.wa_id) if contact else None
            threads.append(
                HistoryThread(
                    user=self._create_user_base_from_contacts(webhook, identity or ""),
                    messages=tuple(
                        [
                            self._history_message(m, outbound=False)
                            for m in value.messages or []
                        ]
                        + [
                            self._history_message(m, outbound=True)
                            for m in value.message_echoes or []
                        ]
                    ),
                )
            )
        return HistorySyncWebhook(
            inbox=inbox_base,
            threads=tuple(threads),
            phase=phase,
            chunk_order=chunk_order,
            progress=progress,
            timestamp=datetime.now(UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )

    def _create_connection_webhook(
        self, webhook: WhatsAppWebhook, field: str, inbox_base: InboxBase
    ) -> InboxConnectionWebhook:
        """Coexistence ``account_offboarded`` / ``account_reconnected``."""
        from wappa.webhooks.core.webhook_interfaces import (
            InboxConnectionState,
            InboxConnectionWebhook,
        )

        account = webhook.get_account_event(field)
        if account is None:
            raise ProcessorError(
                f"No {field} found in webhook",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,
            )
        return InboxConnectionWebhook(
            inbox=inbox_base,
            state=InboxConnectionState.DISCONNECTED
            if field == "account_offboarded"
            else InboxConnectionState.RECONNECTED,
            reason=account.reason,
            account_id=account.waba_id,
            timestamp=datetime.fromtimestamp(account.timestamp, tz=UTC),
            platform=PlatformType.WHATSAPP,
            webhook_id=webhook.get_webhook_id(),
        )
