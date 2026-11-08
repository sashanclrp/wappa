"""One Instagram send and its result: recipient shapes, the result mapping, multi-part folding."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from wappa.domain.message_parts import message_part, with_message_parts
from wappa.domain.messaging_targets import (
    DirectMessage,
    MessageTarget,
    PrivateReply,
    UnsupportedOperationError,
    require_direct_message,
)
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.messaging.meta.graph import GraphResponse

from ..payloads.text import split_text
from ._base import _InstagramBase

PARTS_KEY = "wappa_parts"
REPLY_TO_KEY = "wappa_reply_to"


def _part(
    message: dict[str, Any], result: MessageResult | None = None
) -> dict[str, Any]:
    """Describe one planned Platform message; no recipient or credential values."""
    attachment = message.get("attachment", {})
    payload = attachment.get("payload", {})
    template = payload.get("template_type")
    role = "text_chunk"
    text = message.get("text")
    if "quick_replies" in message:
        role = "quick_replies"
    elif template == "button":
        role, text = "buttons", payload.get("text")
    elif template == "generic":
        role, text = "carousel", None
    elif attachment:
        role, text = "media", None
    part = message_part(role, text, result)
    if result and (result.platform_response or {}).get(REPLY_TO_KEY, {}).get("dropped"):
        part["reply_to_dropped"] = True
    return part


class _Parts:
    """Flatten attempted and skipped messages without changing send control flow."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.parts: list[dict[str, Any]] = []
        self.reply_to: dict[str, Any] | None = None

    def add(self, result: MessageResult, *, role: str | None = None) -> bool:
        response = result.platform_response or {}
        reply_to = response.get(REPLY_TO_KEY)
        if reply_to is not None:
            self.reply_to = reply_to
        nested = response.get(PARTS_KEY, {})
        details = deepcopy(nested.get("parts", []))
        if role:
            for part in details:
                if part["role"] == "text_chunk":
                    part["role"] = role
        self.parts.extend(details)
        self.ids.extend(nested.get("message_ids", []))
        return result.success

    def skip(self, message: dict[str, Any], *, role: str | None = None) -> None:
        part = _part(message)
        if role is not None:
            part["role"] = role
        self.parts.append(part)

    def skip_text(self, text: str, *, role: str | None = None) -> None:
        for chunk in split_text(text):
            self.skip({"text": chunk}, role=role)

    def result(
        self, last: MessageResult, *, primary: MessageResult | None = None
    ) -> MessageResult:
        if last.success and primary is not None:
            last = last.model_copy(update={"message_id": primary.message_id})
        response = dict(last.platform_response or {})
        if self.reply_to is not None:
            response[REPLY_TO_KEY] = self.reply_to
        update: dict[str, Any] = {"platform_response": response}
        if not last.success and self.ids:
            update["error"] = (
                f"{last.error or 'part refused'} ({len(self.ids)} earlier part(s) already delivered)"
            )
        return with_message_parts(last.model_copy(update=update), self.parts)


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
        quote_dropped = (
            "reply_to" in body
            and response.outcome is OperationOutcome.REJECTED
            and response.status_code == 400
            and response.error_code == "100/2534002"
        )
        if quote_dropped:
            # This precise rejection proves the quoted send was not accepted.
            # Retry only that part, once; ambiguous outcomes are never retried.
            unquoted = {key: value for key, value in body.items() if key != "reply_to"}
            response = await self._graph.request(
                "POST", self._graph.messages_path, json=unquoted, operation=operation
            )
        result = self._result(response, address, operation)
        if quote_dropped:
            evidence = dict(result.platform_response or {})
            evidence[REPLY_TO_KEY] = {"dropped": True, "error_code": "100/2534002"}
            result = result.model_copy(update={"platform_response": evidence})
        if result.success and result.message_id and self._sent_registry is not None:
            await self._sent_registry.record(self._inbox_ref, result.message_id)
        return with_message_parts(result, [_part(message, result)])

    def _direct(self, target: DirectMessage, operation: str) -> DirectMessage:
        direct = require_direct_message(target, f"Instagram {operation}")
        direct.resolve(self._inbox_ref)
        return direct
