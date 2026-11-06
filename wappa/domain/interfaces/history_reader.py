"""Conversation history reads: the pull half of one backfill contract.

ADR-0025: history backfill has one typed shape, ``HistoryThread`` of
``HistoryMessage``. Platforms that push history (WhatsApp Coexistence) deliver
it as ``HistorySyncWebhook``; Platforms that only allow reads (Instagram)
expose this capability. Hosts store both the same way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from wappa.domain.interfaces.conversation_capabilities import ReadResult
from wappa.webhooks.core.webhook_interfaces.conversation_webhooks import (
    HistoryThread,
)


class HistoryPage(BaseModel):
    """One page of a User's past messages, newest first as the Platform pages."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    thread: HistoryThread
    next_cursor: str | None = None


class IConversationHistoryReader(ABC):
    """Read past messages exchanged with one User of this Inbox."""

    @abstractmethod
    async def read_history(
        self, user_id: str, *, limit: int = 20, after: str | None = None
    ) -> ReadResult[HistoryPage]: ...


__all__ = ["HistoryPage", "IConversationHistoryReader"]
