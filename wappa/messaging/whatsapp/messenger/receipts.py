"""Read receipts and the typing indicator (``mark_as_read``)."""

from __future__ import annotations

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DirectMessage, require_direct_message
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger._base import _WhatsAppMessengerBase
from wappa.schemas.core.types import PlatformType


class _ReceiptsMixin(_WhatsAppMessengerBase):
    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        # The read receipt is addressed by message ID; ``target`` is only
        # checked against this Inbox.
        require_direct_message(target, "WhatsApp mark_as_read").resolve(
            InboxRef.whatsapp(self._inbox_id)
        )
        try:
            # Cloud API: typing_indicator rides on the read receipt itself and
            # needs only the inbound message ID.
            read_payload = self._message_payloads.create_read_status_message(
                message_id=message_id, typing=typing
            )

            self.logger.debug(f"Marking message {message_id} as read")
            await self.client.post_request(read_payload)

            action_msg = (
                "marked as read with typing indicator" if typing else "marked as read"
            )
            self.logger.info(f"Message {message_id} {action_msg}")

            return MessageResult(
                success=True,
                message_id=message_id,
                recipient=None,
                recipient_bsuid=None,
                recipient_phone=None,
                platform=PlatformType.WHATSAPP,
                inbox_id=self._inbox_id,
            )

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation=(
                    "mark as read with typing indicator" if typing else "mark as read"
                ),
                recipient=message_id,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
