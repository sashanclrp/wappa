"""One WhatsApp send and its result: Delivery Address fallback (ADR-0022) and error results."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from wappa.domain.inbox.identity import InboxRef
from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult
from wappa.messaging.whatsapp.errors import ADDRESS_REJECTION_CODES
from wappa.messaging.whatsapp.messenger._base import _WhatsAppMessengerBase
from wappa.messaging.whatsapp.models.basic_models import message_result_from_payload
from wappa.schemas.core.recipient import BSUID_ERROR_TAG, whatsapp_delivery_order
from wappa.schemas.core.types import PlatformType


class _DeliveryMixin(_WhatsAppMessengerBase):
    def _error_result(
        self, error: str, error_code: str, recipient: str | None = None
    ) -> MessageResult:
        return MessageResult(
            success=False,
            platform=PlatformType.WHATSAPP,
            recipient=recipient,
            recipient_bsuid=None,
            recipient_phone=None,
            error=error,
            error_code=error_code,
            inbox_id=self._inbox_id,
        )

    async def _post_payload(
        self, payload: dict[str, Any], recipient: str
    ) -> MessageResult:
        """Post one payload and read the accepted body as a ``MessageResult``."""
        response = await self.client.post_request(payload)
        return message_result_from_payload(
            response,
            inbox_id=self._inbox_id,
            fallback_recipient=recipient,
        )

    async def _deliver(
        self,
        target: DirectMessage,
        send: Callable[[str], Awaitable[MessageResult]],
        *,
        phone_only: bool = False,
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
        )
        if not addresses:
            return self._error_result(
                "No phone number known for a message that requires one",
                BSUID_ERROR_TAG,
                recipient=target.address,
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
                    "Delivery Address %s rejected (%s); trying the next known address",
                    address,
                    result.error_code,
                )
        assert result is not None
        if len(attempted) > 1:
            result = result.model_copy(
                update={"attempted_recipients": tuple(attempted)}
            )
        return result
