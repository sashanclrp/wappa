"""Text sends: private reply, and DM text split at the byte limit."""

from __future__ import annotations

from typing import Any

from wappa.domain.interactive import check_text
from wappa.domain.messaging_targets import DirectMessage, MessageTarget, PrivateReply
from wappa.domain.results import MessageResult

from ..payloads.text import check_instagram_text, split_text
from ._base import _InstagramBase
from .delivery import _Parts


class _TextMixin(_InstagramBase):
    async def send_text(
        self,
        text: str,
        target: MessageTarget,
        reply_to_message_id: str | None = None,
        disable_preview: bool = False,
    ) -> MessageResult:
        """Text over 1000 UTF-8 bytes goes out as several messages.

        The shared ``TEXT_MAX`` (WhatsApp's 4096 characters) is checked first.
        ``disable_preview`` is ignored: Instagram has no preview switch. A
        ``PrivateReply`` is one message per comment, so it cannot be split and
        an over-limit private reply raises ``ValueError``. For a split text
        the suppressed-quote evidence goes on the first message, and the last result
        returns unless one is refused; that refusal returns and later chunks
        are not sent. Instagram quote IDs are currently ignored before I/O.

        ``reply_to_message_id`` is temporarily ignored on Instagram; result evidence records the dropped quote.
        """
        _ = disable_preview
        if not isinstance(target, DirectMessage | PrivateReply):
            raise TypeError("send_text requires a DirectMessage or PrivateReply")
        # Validate target scope before content so wrong-Inbox fails first.
        target.resolve(self._inbox_ref)
        check_text(text)
        if isinstance(target, PrivateReply):
            return await self._send(
                target,
                {"text": check_instagram_text(text)},
                operation="Instagram private reply",
                reply_to_message_id=reply_to_message_id,
            )
        return await self._send_texts(text, target, reply_to_message_id)

    async def _send_texts(
        self,
        text: str,
        direct: DirectMessage,
        reply_to_message_id: str | None,
        last: dict[str, Any] | None = None,
        operation: str = "Instagram text send",
    ) -> MessageResult:
        """Send ``text`` in ≤ 1000-byte chunks; ``last`` extends the final one.

        ``last`` carries extra message fields (quick replies) on the final
        chunk. Several chunks return one result listing every part (``_Parts``);
        the first refusal stops the send.
        """
        if not text or not text.strip():
            raise ValueError("Instagram text must not be empty")
        chunks = split_text(text)
        if len(chunks) == 1 and not last:
            return await self._send(
                direct,
                {"text": chunks[0]},
                operation=operation,
                reply_to_message_id=reply_to_message_id,
            )
        parts = _Parts()
        result: MessageResult | None = None
        stopped = False
        for index, chunk in enumerate(chunks):
            final = index == len(chunks) - 1
            message: dict[str, Any] = {"text": chunk}
            if final and last:
                message.update(last)
            if stopped:
                parts.skip(message)
                continue
            result = await self._send(
                direct,
                message,
                operation=operation if final else "Instagram text send",
                reply_to_message_id=reply_to_message_id if index == 0 else None,
            )
            stopped = not parts.add(result)
        assert result is not None
        return parts.result(result)
