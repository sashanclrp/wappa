"""Acknowledgement: seen and typing sender actions behind ``mark_as_read``."""

from __future__ import annotations

from wappa.domain.messaging_targets import DirectMessage
from wappa.domain.results import MessageResult, OperationOutcome
from wappa.messaging.meta.graph import GraphResponse

from ._base import _InstagramBase


class _ReceiptsMixin(_InstagramBase):
    async def _sender_action(self, target: DirectMessage, action: str) -> GraphResponse:
        recipient = target.resolve(self._inbox_ref)
        return await self._graph.request(
            "POST",
            self._graph.messages_path,
            json={"recipient": {"id": recipient}, "sender_action": action},
            operation=f"Instagram {action}",
        )

    async def mark_as_read(
        self,
        message_id: str,
        target: DirectMessage,
        *,
        typing: bool = False,
    ) -> MessageResult:
        """``mark_seen`` on the thread, then ``typing_on`` when ``typing``.

        Instagram has no per-message read, so ``target`` names the thread and
        ``message_id`` is echoed in the result. Typing is attempted only after
        the seen action was accepted.
        """
        direct = self._direct(target, "mark_as_read")
        seen = await self._sender_action(direct, "mark_seen")
        typed = (
            await self._sender_action(direct, "typing_on")
            if typing and seen.outcome is OperationOutcome.ACCEPTED
            else None
        )
        failed = next(
            (
                r
                for r in (seen, typed)
                if r is not None and r.outcome is not OperationOutcome.ACCEPTED
            ),
            None,
        )
        error_code = None
        if failed is not None:
            error_code = failed.error_code or (
                "INDETERMINATE"
                if failed.outcome is OperationOutcome.INDETERMINATE
                else None
            )
        return MessageResult(
            success=failed is None,
            platform=self.platform,
            inbox_id=self.inbox_id,
            message_id=message_id,
            recipient=direct.recipient_id,
            recipient_platform_id=direct.recipient_id,
            error=failed.error if failed else None,
            error_code=error_code,
            error_evidence=failed.error_evidence if failed else None,
            retry_after=failed.retry_after if failed else None,
            platform_response={
                "mark_seen": seen.outcome.value,
                "typing_on": typed.outcome.value if typed else None,
            },
        )
