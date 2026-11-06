"""WhatsApp connector (Embedded Signup, Tech Provider flow, Graph v26.0).

Implements :class:`IInboxConnector` on the shared Meta Business Login core:

1. Code exchange → Business Integration System User token (the long-lived
   credential to persist). A code from the JavaScript SDK popup is exchanged
   without ``redirect_uri`` (``MetaLoginConfig(redirect_uri=None)``).
2. ``/debug_token`` → shared WABA IDs (``shared_waba_ids``, or the
   ``whatsapp_business_management`` granular ``target_ids``) and scopes.
3. ``GET /{waba}/phone_numbers`` → one Inbox per phone number
   (``inbox_id`` = ``phone_number_id``, Platform Account = WABA).
4. Activation: ``POST /{waba}/subscribed_apps`` so webhooks fire.
5. Disconnect: ``DELETE /{waba}/subscribed_apps``. This stops delivery for
   every number in that WABA, so Hosts call it only when no other active
   Inbox shares the WABA.

Phone-number ``/register`` (two-step PIN) is not called: Embedded Signup
coexistence numbers are already registered. A new-number path would add it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx
from pydantic import SecretStr

from wappa.domain.inbox.credentials import CredentialRecord
from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.services import InboxCredentialService
from wappa.schemas.core.types import PlatformType

from .contract import (
    ActivationResult,
    AuthorizationRequest,
    ConnectionGrant,
    ConnectionProviderError,
    DiscoveredInbox,
    IConnectionIntentStore,
    IInboxConnector,
    InboxReadiness,
    build_record,
    require_platform,
)
from .meta_login import MetaBusinessLogin, MetaLoginConfig

MANAGEMENT_SCOPE = "whatsapp_business_management"
MESSAGING_SCOPE = "whatsapp_business_messaging"
REQUIRED_WHATSAPP_SCOPES: frozenset[str] = frozenset(
    {MANAGEMENT_SCOPE, MESSAGING_SCOPE}
)
EMBEDDED_SIGNUP_EXTRAS: dict[str, Any] = {"sessionInfoVersion": "3"}


def whatsapp_readiness(scopes: Sequence[str]) -> InboxReadiness:
    missing = sorted(REQUIRED_WHATSAPP_SCOPES - set(scopes))
    return InboxReadiness(
        conversation_ready=not missing, missing_required_scopes=tuple(missing)
    )


def shared_waba_ids(debug: dict[str, Any]) -> tuple[str, ...]:
    """WABA IDs shared with the app, from either ``debug_token`` shape."""
    direct = debug.get("shared_waba_ids")
    if isinstance(direct, list) and direct:
        return tuple(str(i) for i in direct)
    for scope in debug.get("granular_scopes", []) or []:
        if isinstance(scope, dict) and scope.get("scope") == MANAGEMENT_SCOPE:
            return tuple(str(t) for t in scope.get("target_ids") or [])
    return ()


class WhatsAppConnector(IInboxConnector):
    """WhatsApp phone numbers as Inboxes, via Embedded Signup."""

    def __init__(
        self,
        config: MetaLoginConfig,
        *,
        client_provider: Callable[[], httpx.AsyncClient],
        intent_store: IConnectionIntentStore,
        clock: Callable[[], float] = time.time,
        state_ttl_seconds: int = 600,
    ) -> None:
        if config.dialog_extras is None:
            config = config.model_copy(
                update={"dialog_extras": dict(EMBEDDED_SIGNUP_EXTRAS)}
            )
        self._login = MetaBusinessLogin(
            config,
            client_provider=client_provider,
            intent_store=intent_store,
            clock=clock,
            state_ttl_seconds=state_ttl_seconds,
        )

    @property
    def platform(self) -> PlatformType:
        return PlatformType.WHATSAPP

    async def begin(
        self, host_subject: str, *, metadata: dict[str, str] | None = None
    ) -> AuthorizationRequest:
        return await self._login.begin(host_subject, metadata=metadata)

    async def complete(
        self,
        *,
        state: str | None,
        host_subject: str,
        code: str | None = None,
        error: str | None = None,
        error_reason: str | None = None,
    ) -> ConnectionGrant:
        grant, debug = await self._login.authorize(
            PlatformType.WHATSAPP,
            state=state,
            host_subject=host_subject,
            code=code,
            error=error,
            error_reason=error_reason,
        )
        wabas = shared_waba_ids(debug)
        if not wabas:
            raise ConnectionProviderError(
                "Embedded Signup shared no WhatsApp Business Account", "NO_WABA"
            )
        inboxes: list[DiscoveredInbox] = []
        for waba_id in wabas:
            readiness = whatsapp_readiness(grant.scopes_for(waba_id))
            for number in await self._phone_numbers(waba_id, grant.access_token):
                inboxes.append(
                    DiscoveredInbox(
                        inbox_ref=InboxRef.whatsapp(str(number["id"])),
                        account_ref=PlatformAccountRef.whatsapp(waba_id),
                        display_name=number.get("verified_name")
                        or number.get("display_phone_number"),
                        readiness=readiness,
                    )
                )
        return grant.model_copy(update={"inboxes": tuple(inboxes)})

    async def _phone_numbers(
        self, waba_id: str, token: SecretStr
    ) -> list[dict[str, Any]]:
        body = await self._login.get(
            f"{waba_id}/phone_numbers",
            {"fields": "id,display_phone_number,verified_name"},
            token=token,
        )
        return [
            row
            for row in body.get("data", []) or []
            if isinstance(row, dict) and row.get("id")
        ]

    async def activate(
        self,
        grant: ConnectionGrant,
        inbox_ref: InboxRef,
        *,
        credentials: InboxCredentialService,
        previous: CredentialRecord | None = None,
    ) -> ActivationResult:
        """Subscribe the app to the number's WABA, then build the encrypted record."""
        require_platform(self.platform, grant, inbox_ref)
        inbox = grant.inbox(inbox_ref)
        waba_id = inbox.account_ref.platform_account_id
        ok, code = await self._login.success_call(
            "POST", f"{waba_id}/subscribed_apps", grant.access_token
        )
        outcome = "subscribed" if ok else "unknown" if ok is None else "rejected"
        return ActivationResult(
            inbox_ref=inbox_ref,
            record=build_record(
                credentials, inbox, grant.access_token, previous=previous
            ),
            webhooks_subscribed=bool(ok),
            details={"waba_subscribed_apps": outcome},
            error_code=code,
        )

    async def disconnect(
        self, inbox_ref: InboxRef, account_ref: PlatformAccountRef, token: SecretStr
    ) -> bool:
        """Unsubscribe the app from the WABA (``account_ref``) of ``inbox_ref``.

        WhatsApp subscriptions are per WABA: this stops webhooks for every
        number in it, so call it only when no other active Inbox shares it.
        """
        _ = inbox_ref
        ok, _code = await self._login.success_call(
            "DELETE", f"{account_ref.platform_account_id}/subscribed_apps", token
        )
        return bool(ok)


__all__ = [
    "EMBEDDED_SIGNUP_EXTRAS",
    "REQUIRED_WHATSAPP_SCOPES",
    "WhatsAppConnector",
    "shared_waba_ids",
    "whatsapp_readiness",
]
