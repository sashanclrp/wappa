"""One WhatsApp send and its result: Delivery Address fallback (ADR-0022) and error results."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.message_parts import message_part, with_message_parts
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import (
    ADDRESS_REJECTION_CODES,
    handle_whatsapp_error,
)
from wappa.messaging.whatsapp.messenger._base import _WhatsAppMessengerBase
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.messaging.whatsapp.part_content import message_content
from wappa.schemas.core.recipient import BSUID_ERROR_TAG, whatsapp_delivery_order
from wappa.schemas.core.types import PlatformType


class _DeliveryMixin(_WhatsAppMessengerBase):
    def _error_result(
        self, error: str, error_code: str, recipient: str | None = None
    ) -> MessageResult:
        result = MessageResult(
            success=False,
            platform=PlatformType.WHATSAPP,
            recipient=recipient,
            recipient_bsuid=None,
            recipient_phone=None,
            error=error,
            error_code=error_code,
            inbox_id=self._inbox_id,
        )

        return with_message_parts(result, [message_part("message", None, result)])

    async def _post_payload(
        self, payload: dict[str, Any], recipient: str, *, custom_url: str | None = None
    ) -> MessageResult:
        """Post one payload and read the accepted body as a ``MessageResult``."""
        content = message_content(payload)
        try:
            response = (
                await self.client.post_request(payload, custom_url=custom_url)
                if custom_url
                else await self.client.post_request(payload)
            )
            result = message_result_from_payload(
                response, inbox_id=self._inbox_id, fallback_recipient=recipient
            )
        except Exception as error:
            result = handle_whatsapp_error(
                error, f"send {payload['type']}", recipient, self._inbox_id, self.logger
            )
        return with_message_parts(
            result, [message_part("message", None, result, content=content)]
        )

    async def _deliver(
        self,
        target: DirectMessage,
        send: Callable[[str], Awaitable[MessageResult]],
        *,
        phone_only: bool = False,
        part_role: str = "message",
        part_text: str | None = None,
    ) -> MessageResult:
        """Send to the User's addresses in WhatsApp order, falling back once
        per address only when Meta rejects the address itself.

        Order: phone (``wa_id``) first, then BSUID, as Meta recommends. A
        rejection that is not about the address (window, rate limit, content,
        timeouts) is returned as-is: retrying could not help or could send
        twice. ``phone_only`` covers authentication Templates, which Meta
        does not deliver to BSUIDs.
        """
        addresses = whatsapp_delivery_order(
            target.resolve_all(InboxRef.whatsapp(self._inbox_id)),
            phone_only=phone_only,
            evidence=target.addresses.evidence,
        )
        if not addresses:
            failure = self._error_result(
                "No phone number known for a message that requires one",
                BSUID_ERROR_TAG,
                recipient=target.address,
            )
            return with_message_parts(
                failure, [message_part(part_role, part_text, failure)]
            )
        attempted: list[str] = []
        result: MessageResult | None = None
        for address in addresses:
            attempted.append(address)
            result = await send(address)
            if result.success or result.error_code not in ADDRESS_REJECTION_CODES:
                break
            if address != addresses[-1]:
                self.logger.warning(
                    "Delivery Address rejected (%s); trying the next known address",
                    result.error_code,
                )
        assert result is not None
        if len(attempted) > 1:
            result = result.model_copy(
                update={"attempted_recipients": tuple(attempted)}
            )
        return with_message_parts(
            result,
            [
                message_part(
                    part_role,
                    part_text,
                    result,
                    content=result.parts[0].content if result.parts else None,
                )
            ],
        )
