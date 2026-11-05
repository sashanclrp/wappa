"""Inbox Connector: one contract for connecting accounts on every Platform.

Connecting an account so it becomes an Inbox is the same action on every
Platform (ADR-0017), and a separate responsibility from messaging: it runs
before a Messenger exists and produces the Wappa-encrypted credential record
that a Messenger later uses.

Lifecycle::

    begin(host_subject)            → AuthorizationRequest (redirect the operator)
    complete(state, code, ...)     → ConnectionGrant (discovered Inboxes + readiness)
    activate(grant, inbox_ref, …)  → ActivationResult (webhooks + encrypted record)
    disconnect(inbox_ref, account_ref, token) → stop that account's webhooks

Ownership: Wappa owns protocol translation, one-use state binding, discovery,
scope evidence, webhook subscription and record encryption. The Host owns the
authenticated operator, intent storage, routes/UI, Owner/Channel mapping,
transactions and calling ``refresh_inbox`` after it commits the record.
Tokens only ever leave as ``SecretStr`` inside a grant.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.services import InboxCredentialService
from wappa.schemas.core.types import PlatformType

# ── errors ───────────────────────────────────────────────────────────────


class InboxConnectionError(Exception):
    """Base class for connection failures on any Platform."""


class ConnectionStateError(InboxConnectionError):
    """Unknown, expired, replayed or mismatched connection state."""


class ConnectionCancelledError(InboxConnectionError):
    """The operator cancelled or denied the authorization dialog."""


class ConnectionProviderError(InboxConnectionError):
    """The Platform rejected a connection call; ``code`` is its error code."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


# ── one-use connection intent (Host-stored) ──────────────────────────────


@dataclass(frozen=True, slots=True)
class ConnectionIntent:
    """Host-authenticated intent bound to one authorization attempt."""

    state: str
    host_subject: str
    created_at: float
    expires_at: float
    metadata: dict[str, str] = field(default_factory=dict)


class IConnectionIntentStore(Protocol):
    """Host-owned durable intent storage; ``consume`` must be atomic/one-use."""

    async def save(self, intent: ConnectionIntent) -> None: ...

    async def consume(self, state: str) -> ConnectionIntent | None: ...


class InMemoryConnectionIntentStore:
    """Single-process store for examples/tests (not for multi-worker hosts)."""

    def __init__(self) -> None:
        self._items: dict[str, ConnectionIntent] = {}

    async def save(self, intent: ConnectionIntent) -> None:
        self._items[intent.state] = intent

    async def consume(self, state: str) -> ConnectionIntent | None:
        return self._items.pop(state, None)


# ── results ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Where to send the operator; ``state`` is bound to the Host subject."""

    url: str
    state: str
    expires_at: float


class InboxReadiness(BaseModel):
    """Whether a discovered Inbox can hold conversations, plus optional features.

    ``features`` names optional, Platform-specific abilities (for example
    Instagram ``comments``) and whether the grant covers them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    conversation_ready: bool
    missing_required_scopes: tuple[str, ...] = ()
    features: dict[str, bool] = Field(default_factory=dict)
    granted_optional_scopes: tuple[str, ...] = ()
    missing_optional_scopes: tuple[str, ...] = ()


class DiscoveredInbox(BaseModel):
    """An account the grant can connect, already expressed as Wappa identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    inbox_ref: InboxRef
    account_ref: PlatformAccountRef
    display_name: str | None = None
    readiness: InboxReadiness


class ConnectionGrant(BaseModel):
    """Outcome of a completed authorization. Persist only via encrypted records."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    platform: PlatformType
    intent_subject: str
    access_token: SecretStr
    inboxes: tuple[DiscoveredInbox, ...]
    granted_scopes: tuple[str, ...] = ()
    scope_targets: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    expires_at: int | None = None

    def inbox(self, inbox_ref: InboxRef) -> DiscoveredInbox:
        for found in self.inboxes:
            if found.inbox_ref == inbox_ref:
                return found
        raise ValueError(f"{inbox_ref} was not discovered by this grant")

    def scopes_for(self, target_id: str) -> tuple[str, ...]:
        """Granted scopes that apply to one asset (granular targets respected)."""
        return tuple(
            scope
            for scope in self.granted_scopes
            # No granular targets means the scope is not asset-restricted.
            if not self.scope_targets.get(scope)
            or target_id in self.scope_targets[scope]
        )


class ActivationResult(BaseModel):
    """Activation evidence plus the record the Host must persist, then refresh."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    inbox_ref: InboxRef
    record: Any = Field(description="Wappa-encrypted active CredentialRecord")
    webhooks_subscribed: bool
    details: dict[str, str] = Field(
        default_factory=dict,
        description="Per-item outcomes, e.g. Instagram field → subscribed/rejected",
    )
    error_code: str | None = None


# ── the contract ─────────────────────────────────────────────────────────


class IInboxConnector(ABC):
    """Connect, activate and disconnect accounts of one Platform as Inboxes."""

    @property
    @abstractmethod
    def platform(self) -> PlatformType: ...

    @abstractmethod
    async def begin(
        self, host_subject: str, *, metadata: dict[str, str] | None = None
    ) -> AuthorizationRequest:
        """Bind a one-use state to the Host's authenticated subject."""

    @abstractmethod
    async def complete(
        self,
        *,
        state: str | None,
        host_subject: str,
        code: str | None = None,
        error: str | None = None,
        error_reason: str | None = None,
    ) -> ConnectionGrant:
        """Consume the state, exchange the code and discover connectable Inboxes."""

    @abstractmethod
    async def activate(
        self,
        grant: ConnectionGrant,
        inbox_ref: InboxRef,
        *,
        credentials: InboxCredentialService,
        previous: Any | None = None,
    ) -> ActivationResult:
        """Subscribe webhooks and build the encrypted record (rotating ``previous``)."""

    @abstractmethod
    async def disconnect(
        self, inbox_ref: InboxRef, account_ref: PlatformAccountRef, token: SecretStr
    ) -> bool:
        """Stop webhook delivery for the Inbox's account; ``True`` when confirmed.

        Pass the record's ``inbox_ref`` and ``account_ref``. Where webhooks are
        subscribed per Platform Account (a WhatsApp WABA), this stops delivery
        for every Inbox in that account.
        """


def build_record(
    credentials: InboxCredentialService,
    inbox: DiscoveredInbox,
    token: SecretStr,
    *,
    previous: Any | None = None,
) -> Any:
    """Wappa-encrypted canonical record; rotates when a previous record exists."""
    if previous is not None:
        if previous.inbox_ref != inbox.inbox_ref:
            raise ValueError("previous record belongs to a different Inbox")
        if not previous.is_active:
            raise ValueError(
                "previous record is inactive; reconnect deliberately with a new record"
            )
        return credentials.rotate_active_record(
            previous, access_token=token, account_ref=inbox.account_ref
        )
    return credentials.create_active_record(
        inbox_ref=inbox.inbox_ref, account_ref=inbox.account_ref, access_token=token
    )


__all__ = [
    "ActivationResult",
    "AuthorizationRequest",
    "ConnectionCancelledError",
    "ConnectionGrant",
    "ConnectionIntent",
    "ConnectionProviderError",
    "ConnectionStateError",
    "DiscoveredInbox",
    "IConnectionIntentStore",
    "IInboxConnector",
    "InMemoryConnectionIntentStore",
    "InboxConnectionError",
    "InboxReadiness",
    "build_record",
]
