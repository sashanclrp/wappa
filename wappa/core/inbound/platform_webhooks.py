"""The inbound Platform seam: route an authenticated batch, then translate it.

Every installed Platform supplies one ``PlatformWebhooks`` adapter through
``wappa.platforms``. The webhook controller authenticates the request bytes
(ADR-0023) and calls ``route``; the Inbound Runtime runs admission and echo
proof, then calls ``translate`` (ADR-0023). Message-type tables stay private
to each adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials

if TYPE_CHECKING:
    from wappa.schemas.core.types import PlatformType
    from wappa.webhooks.core.webhook_interfaces.universal_webhooks import (
        UniversalWebhook,
    )


class PayloadRoutingError(Exception):
    """An authenticated payload cannot identify a safe dispatch scope."""


@dataclass(frozen=True, slots=True)
class RoutedWebhookDelivery:
    """One Platform change bound to one validated Inbox."""

    inbox_ref: InboxRef
    account_ref: PlatformAccountRef
    credentials: ResolvedInboxCredentials
    payload: dict[str, Any]

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id


class PlatformWebhooks(Protocol):
    """One Platform's inbound adapter.

    ``route`` may do credential I/O and raises ``PayloadRoutingError`` or the
    Inbox Directory error family. ``translate`` is pure: one routed delivery
    payload in, one Universal Webhook out, no I/O.
    """

    @property
    def platform(self) -> PlatformType:
        """The Platform this adapter serves."""
        ...

    @property
    def builtin_fields(self) -> frozenset[str]:
        """Webhook field names the adapter handles natively (reserved)."""
        ...

    async def route(
        self, payload: dict[str, Any], resolver: IInboxCredentialResolver
    ) -> tuple[RoutedWebhookDelivery, ...]:
        """Split an authenticated batch and bind each unit to a validated Inbox."""
        ...

    async def translate(
        self, payload: dict[str, Any], *, inbox_id: str
    ) -> UniversalWebhook:
        """Translate one routed delivery payload into a Universal Webhook."""
        ...


__all__ = [
    "PayloadRoutingError",
    "PlatformWebhooks",
    "RoutedWebhookDelivery",
]
