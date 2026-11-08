"""Text sends (``send_text``)."""

from __future__ import annotations

from wappa.domain.interactive import check_text
from wappa.domain.messaging_targets import MessageTarget, require_direct_message
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import handle_whatsapp_error
from wappa.messaging.whatsapp.messenger.delivery import _DeliveryMixin
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload


class _TextMixin(_DeliveryMixin):
    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        check_text(text)
        return await self._deliver(
            require_direct_message(target, "WhatsApp send_text"),
            lambda recipient: self._send_text_to(
                recipient, text, reply_to_message_id, disable_preview
            ),
            part_role="text_chunk",
            part_text=text,
        )

    async def _send_text_to(
        self,
        recipient: str,
        text: str,
        reply_to_message_id: str | None,
        disable_preview: bool,
    ) -> MessageResult:
        try:
            payload = self._message_payloads.create_text_message(
                text=text,
                recipient=recipient,
                reply_to_message_id=reply_to_message_id,
                disable_preview=disable_preview,
            )

            self.logger.debug("Sending text message")
            response = await self.client.post_request(payload)
            result = message_result_from_payload(
                response,
                inbox_id=self._inbox_id,
                fallback_recipient=recipient,
            )
            self.logger.info(f"Text message sent successfully, id: {result.message_id}")
            return result

        except Exception as e:
            return handle_whatsapp_error(
                error=e,
                operation="send text message",
                recipient=recipient,
                inbox_id=self._inbox_id,
                logger=self.logger,
            )
