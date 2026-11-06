"""Instagram conversation history reads (``IConversationHistoryReader``).

Endpoints (Instagram API with Instagram Login, v26.0):

1. ``GET /{ig-user-id}/conversations?platform=instagram&user_id={IGSID}``
   → the conversation with that User.
2. ``GET /{conversation-id}/messages?fields=id,created_time,from,to,message,
   attachments&limit=n[&after=]`` → messages, newest first.

Meta returns message details only for the 20 most recent messages of a
conversation, so ``limit`` is capped at 20.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from wappa.domain.interfaces.conversation_capabilities import ReadOutcome, ReadResult
from wappa.domain.interfaces.history_reader import (
    HistoryPage,
    IConversationHistoryReader,
)
from wappa.schemas.core.types import MessageType
from wappa.webhooks.core.base_message import BaseMessage
from wappa.webhooks.core.webhook_interfaces.base_components import UserBase
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    HistoryDirection,
    HistoryMessage,
    HistoryThread,
)
from wappa.webhooks.instagram.models import (
    ATTACHMENT_CLASSES,
    InstagramAttachment,
    InstagramTextMessage,
)

from .client import InstagramClient
from .content import _read_failure

MAX_HISTORY_PAGE = 20
MESSAGE_FIELDS = "id,created_time,from,to,message,attachments"

# Conversations API attachment keys → webhook attachment types.
_ATTACHMENT_KEYS = (
    ("image_data", "image"),
    ("video_data", "video"),
    ("audio_data", "audio"),
)


def _when(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("+0000", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _attachment(raw: dict[str, Any]) -> InstagramAttachment | None:
    for key, kind in _ATTACHMENT_KEYS:
        data = raw.get(key)
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            return InstagramAttachment(type=kind, payload={"url": data["url"]})
    if isinstance(raw.get("file_url"), str):
        return InstagramAttachment(type="file", payload={"url": raw["file_url"]})
    return None


class InstagramHistoryReader(IConversationHistoryReader):
    def __init__(self, graph: InstagramClient) -> None:
        self._graph = graph

    @property
    def _account_id(self) -> str:
        return self._graph.inbox_ref.inbox_id

    def _typed(
        self, raw: dict[str, Any], sender: str, when: datetime
    ) -> tuple[BaseMessage | None, str]:
        common: dict[str, Any] = {
            "id": raw["id"],
            "sender": sender,
            "account_id": self._account_id,
            "timestamp_ms": max(1, int(when.timestamp() * 1000)),
        }
        text = raw.get("message") if isinstance(raw.get("message"), str) else None
        attachments = (raw.get("attachments") or {}).get("data") or []
        found = [a for a in (_attachment(x) for x in attachments) if a is not None]
        if found:
            kind = ATTACHMENT_CLASSES[found[0].type]
            return kind(**common, attachments=tuple(found), text=text), found[0].type
        if text:
            return InstagramTextMessage(**common, text=text), "text"
        return None, "attachment" if attachments else "unknown"

    def _message(self, raw: dict[str, Any]) -> HistoryMessage | None:
        if not isinstance(raw.get("id"), str):
            return None
        sender = str((raw.get("from") or {}).get("id") or "")
        when = _when(raw.get("created_time"))
        message, native_type = self._typed(raw, sender, when)
        message_type: MessageType | None = (
            message.message_type if message is not None else None
        )
        return HistoryMessage(
            message_id=raw["id"],
            direction=HistoryDirection.OUTBOUND
            if sender == self._account_id
            else HistoryDirection.INBOUND,
            timestamp=when,
            native_type=native_type,
            message_type=message_type,
            message=message,
        )

    async def read_history(
        self, user_id: str, *, limit: int = 20, after: str | None = None
    ) -> ReadResult[HistoryPage]:
        if not 1 <= limit <= MAX_HISTORY_PAGE:
            raise ValueError(f"limit must be between 1 and {MAX_HISTORY_PAGE}")
        found = await self._graph.request(
            "GET",
            f"{self._account_id}/conversations",
            params={"platform": "instagram", "user_id": user_id},
            operation="Instagram conversation lookup",
        )
        if not found.ok:
            return _read_failure(found)
        rows = found.body.get("data") or []
        if not rows or not isinstance(rows[0], dict) or "id" not in rows[0]:
            return ReadResult(outcome=ReadOutcome.NOT_FOUND)
        params: dict[str, Any] = {"fields": MESSAGE_FIELDS, "limit": limit}
        if after:
            params["after"] = after
        page = await self._graph.request(
            "GET",
            f"{rows[0]['id']}/messages",
            params=params,
            operation="Instagram history read",
        )
        if not page.ok:
            return _read_failure(page)
        messages = [
            m
            for m in (self._message(r) for r in page.body.get("data") or [])
            if m is not None
        ]
        cursors = (page.body.get("paging") or {}).get("cursors") or {}
        has_next = bool((page.body.get("paging") or {}).get("next"))
        return ReadResult(
            outcome=ReadOutcome.FOUND,
            value=HistoryPage(
                thread=HistoryThread(
                    user=UserBase(platform_user_id=user_id),
                    messages=tuple(messages),
                ),
                next_cursor=cursors.get("after") if has_next else None,
            ),
        )


__all__ = ["MAX_HISTORY_PAGE", "InstagramHistoryReader"]
