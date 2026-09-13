"""Host-owned context resolution for External Webhook Source events."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from wappa.domain.inbox.identity import InboxRef

if TYPE_CHECKING:
    from fastapi import Request

    from wappa.domain.events.external_event import ExternalEvent

type SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True, slots=True)
class ResolvedExternalWebhookContext:
    """Inbox context selected by a Host Application after webhook validation."""

    inbox_ref: InboxRef
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.inbox_ref, InboxRef):
            raise TypeError("inbox_ref must be an InboxRef")


class IExternalWebhookContextResolver(Protocol):
    """Resolve optional Inbox context from an authenticated external webhook."""

    async def resolve(
        self,
        request: Request,
        event: ExternalEvent,
        db: SessionFactory | None,
        db_read: SessionFactory | None,
    ) -> ResolvedExternalWebhookContext | None:
        """Return concrete Inbox context, or ``None`` for unscoped dispatch."""
        ...
