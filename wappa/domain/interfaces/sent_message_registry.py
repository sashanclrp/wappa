"""Sent-message registry: transient proof of which message IDs Wappa sent.

``OutboundEchoWebhook`` carries only messages sent *outside* Wappa (a person
answering from the Instagram app or the WhatsApp Business app). Instagram
echoes every outbound message, Wappa's own API sends included, so Wappa must
recognise its own sends and drop their echoes (ADR-0023). When the echo names
the sending app (``app_id``) that evidence decides; otherwise this registry
does.

This is runtime correlation state, not conversation storage: it holds only
message IDs, for minutes, so echoes can be matched. Persisting the delivered
events remains the Host's job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from wappa.domain.inbox.identity import InboxRef


class ISentMessageRegistry(ABC):
    """Short-lived, Inbox-scoped set of message IDs this Wappa sent."""

    @abstractmethod
    async def record(self, inbox_ref: InboxRef, message_id: str) -> None:
        """Remember a confirmed send. Must never fail the send."""

    @abstractmethod
    async def claim(self, inbox_ref: InboxRef, message_id: str) -> bool:
        """``True`` when Wappa sent ``message_id``; the entry is then retired.

        Claiming shortens the entry to a brief grace period (for a redelivered
        echo) instead of keeping it for the full TTL, so the registry holds
        only sends whose echo has not arrived yet.
        """


__all__ = ["ISentMessageRegistry"]
