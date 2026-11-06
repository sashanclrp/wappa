"""One Instagram send and its result: recipient shapes, the result mapping, multi-part folding."""

from __future__ import annotations

from typing import Any

from wappa.domain.messaging_targets import (
    DirectMessage,
    MessageTarget,
    PrivateReply,
    UnsupportedOperationError,
    require_direct_message,
)
from wappa.domain.results import MessageResult
from wappa.messaging.meta.graph import GraphResponse

from ._base import _InstagramBase

PARTS_KEY = "wappa_parts"


class _Parts:
    """Fold the messages of one emulated send into one ``MessageResult``.

    An emulation (split text, media header then buttons, caption follow-up,
    carousel intro) is one Host call, so it returns one result: success only
    when every part was accepted, the final part's ``message_id``, and every
    part's ID under ``platform_response["wappa_parts"]``. On a refusal the
    failed result says how many parts were already delivered, so a Host never
    resends the whole message blindly. Nested emulations are flattened.
    """

    def __init__(self) -> None:
        self.ids: list[str] = []

    def add(self, result: MessageResult) -> bool:
        if not result.success:
            return False
        nested = (result.platform_response or {}).get(PARTS_KEY)
        if nested:
            self.ids.extend(nested["message_ids"])
        elif result.message_id:
            self.ids.append(result.message_id)
        return True

    def result(
        self, last: MessageResult, *, primary: MessageResult | None = None
    ) -> MessageResult:
        """``last`` is the final part's result, or the first refused one.

        On success the returned ``message_id`` is ``primary``'s when given
        (the media of a media-plus-caption send), else ``last``'s (the
        interactive message a User taps).
        """
        if last.success and primary is not None:
            last = last.model_copy(update={"message_id": primary.message_id})
        delivered = len(self.ids)
        response = dict(last.platform_response or {})
        response[PARTS_KEY] = {"message_ids": list(self.ids), "delivered": delivered}
        update: dict[str, Any] = {"platform_response": response}
        if not last.success and delivered:
            update["error"] = (
                f"{last.error or 'part refused'} "
                f"({delivered} earlier part(s) already delivered)"
            )
        return last.model_copy(update=update)


class _DeliveryMixin(_InstagramBase):
    def _result(
        self, response: GraphResponse, recipient: str, operation: str
    ) -> MessageResult:
        message_id = response.body.get("message_id") if response.ok else None
        if response.ok and isinstance(message_id, str) and message_id:
            native_recipient = response.body.get("recipient_id")
            return MessageResult(
                success=True,
                platform=self.platform,
                inbox_id=self.inbox_id,
                recipient=native_recipient
                if isinstance(native_recipient, str) and native_recipient
                else recipient,
                message_id=message_id,
                platform_response=response.body,
            )
        if response.ok:
            # 2xx without a message ID: we cannot prove what happened.
            return MessageResult(
                success=False,
                platform=self.platform,
                inbox_id=self.inbox_id,
                recipient=recipient,
                error=f"{operation} outcome is unknown (no message_id); "
                "do not automatically resend",
                error_code="INDETERMINATE",
            )
        return MessageResult(
            success=False,
            platform=self.platform,
            inbox_id=self.inbox_id,
            recipient=recipient,
            error=response.error,
            error_code=response.error_code,
            retry_after=response.retry_after,
        )

    async def _send(
        self,
        target: MessageTarget,
        message: dict[str, Any],
        *,
        operation: str,
        reply_to_message_id: str | None = None,
    ) -> MessageResult:
        if isinstance(target, PrivateReply):
            if reply_to_message_id:
                raise UnsupportedOperationError(
                    "A PrivateReply cannot also reply to a DM message"
                )
            comment_id = target.resolve(self._inbox_ref)
            recipient: dict[str, str] = {"comment_id": comment_id}
            address = target.address
        else:
            address = target.resolve(self._inbox_ref)
            recipient = {"id": address}
        body: dict[str, Any] = {"recipient": recipient, "message": message}
        if reply_to_message_id:
            body["reply_to"] = {"mid": reply_to_message_id}
        response = await self._graph.request(
            "POST", self._graph.messages_path, json=body, operation=operation
        )
        result = self._result(response, address, operation)
        if result.success and result.message_id and self._sent_registry is not None:
            await self._sent_registry.record(self._inbox_ref, result.message_id)
        return result

    def _direct(self, target: DirectMessage, operation: str) -> DirectMessage:
        direct = require_direct_message(target, f"Instagram {operation}")
        direct.resolve(self._inbox_ref)
        return direct
