"""Instagram connector (Instagram API with Unified Login, Graph v26.0).

Implements :class:`IInboxConnector` on the shared Meta Business Login core:

- discovery: ``GET /me/assigned_instagram_accounts?fields=id,username``
  (``/me`` is the business system user, never an Instagram Inbox);
- readiness: ``instagram_basic`` + ``instagram_manage_messages`` are required;
  ``instagram_manage_comments`` enables the ``comments`` feature;
- activation: ``POST /{ig-account-id}/subscribed_apps?subscribed_fields=…``;
- disconnect: ``DELETE /{ig-account-id}/subscribed_apps``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from wappa.domain.inbox.credentials import CredentialRecord
from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.services import InboxCredentialService
from wappa.domain.results import OperationOutcome
from wappa.messaging.instagram.errors import describe_error
from wappa.messaging.meta.graph import GraphResponse, graph_request
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
from .meta_login import MetaBusinessLogin, MetaLoginConfig, as_dict

REQUIRED_CONVERSATION_SCOPES: frozenset[str] = frozenset(
    {"instagram_basic", "instagram_manage_messages"}
)
COMMENT_SCOPES: frozenset[str] = frozenset({"instagram_manage_comments"})
OPTIONAL_EXTENSION_SCOPES: frozenset[str] = frozenset(
    {"instagram_content_publish", "instagram_manage_insights"}
)

CORE_SUBSCRIPTION_FIELDS: tuple[str, ...] = (
    "messages",
    "messaging_postbacks",
    "messaging_seen",
    "messaging_referral",
)
COMMENT_SUBSCRIPTION_FIELDS: tuple[str, ...] = (
    "comments",
    "live_comments",
    "mentions",
)
UNVERIFIED_SUBSCRIPTION_FIELDS: tuple[str, ...] = ("message_edit",)
"""Selected but absent from the Unified Login field table; attempted separately."""


def instagram_readiness(scopes: Sequence[str]) -> InboxReadiness:
    granted = set(scopes)
    missing = sorted(REQUIRED_CONVERSATION_SCOPES - granted)
    return InboxReadiness(
        conversation_ready=not missing,
        missing_required_scopes=tuple(missing),
        features={"comments": granted >= COMMENT_SCOPES},
        granted_optional_scopes=tuple(sorted(OPTIONAL_EXTENSION_SCOPES & granted)),
        missing_optional_scopes=tuple(sorted(OPTIONAL_EXTENSION_SCOPES - granted)),
    )


# ── webhook field subscriptions ──────────────────────────────────────────


class FieldSubscriptionOutcome(StrEnum):
    SUBSCRIBED = "subscribed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class SubscriptionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    account_id: str
    fields: dict[str, FieldSubscriptionOutcome]
    error_code: str | None = None

    @property
    def core_subscribed(self) -> bool:
        return all(
            self.fields.get(f) is FieldSubscriptionOutcome.SUBSCRIBED
            for f in CORE_SUBSCRIPTION_FIELDS
            if f in self.fields
        )


def _outcome(response: GraphResponse) -> FieldSubscriptionOutcome:
    """``{"success": true}`` subscribes; any other accepted body is unknown."""
    if response.outcome is OperationOutcome.REJECTED:
        return FieldSubscriptionOutcome.REJECTED
    if response.ok and response.body.get("success") is True:
        return FieldSubscriptionOutcome.SUBSCRIBED
    return FieldSubscriptionOutcome.UNKNOWN


class InstagramSubscriptions:
    """Account-level webhook field subscription (``/{ig-id}/subscribed_apps``).

    Every call goes through the shared Meta ``graph_request``, so the
    accepted / rejected / indeterminate classification matches messaging.
    ``graph_base`` is the versioned Graph root (``MetaLoginConfig.graph_base``).
    """

    def __init__(
        self,
        *,
        client_provider: Callable[[], httpx.AsyncClient],
        graph_base: str,
        app_id: str | None = None,
    ) -> None:
        self._client_provider = client_provider
        self._graph = graph_base.rstrip("/")
        self._app_id = app_id

    async def _call(
        self,
        method: str,
        account_id: str,
        token: SecretStr,
        *,
        params: dict[str, Any] | None = None,
    ) -> GraphResponse:
        return await graph_request(
            self._client_provider(),
            self._graph,
            f"{account_id}/subscribed_apps",
            token,
            method=method,
            operation="Instagram subscribed_apps",
            params=params,
            timeout=20.0,
            describe=describe_error,
        )

    async def _subscribe_call(
        self, account_id: str, token: SecretStr, fields: Sequence[str]
    ) -> tuple[FieldSubscriptionOutcome, str | None]:
        response = await self._call(
            "POST",
            account_id,
            token,
            params={"subscribed_fields": ",".join(fields)},
        )
        outcome = _outcome(response)
        if outcome is FieldSubscriptionOutcome.SUBSCRIBED:
            return outcome, None
        return outcome, response.error_code or "INDETERMINATE"

    async def subscribe(
        self,
        account_id: str,
        token: SecretStr,
        *,
        fields: Sequence[str] = CORE_SUBSCRIPTION_FIELDS + COMMENT_SUBSCRIPTION_FIELDS,
        try_unverified: Sequence[str] = UNVERIFIED_SUBSCRIPTION_FIELDS,
    ) -> SubscriptionResult:
        """Subscribe the account; unverified fields are attempted separately.

        Meta replaces the account's field set on each call, so the unverified
        attempt includes the core fields too. Its rejection leaves the core
        subscription intact and is reported per field.
        """
        subscribed = FieldSubscriptionOutcome.SUBSCRIBED
        outcomes: dict[str, FieldSubscriptionOutcome] = {}
        core, code = await self._subscribe_call(account_id, token, fields)
        outcomes.update(dict.fromkeys(fields, core))
        if core is subscribed and try_unverified:
            extra, _ = await self._subscribe_call(
                account_id, token, [*fields, *try_unverified]
            )
            outcomes.update(dict.fromkeys(try_unverified, extra))
            if extra is not subscribed:
                # Restore the verified set if the combined call failed.
                await self._subscribe_call(account_id, token, fields)
        return SubscriptionResult(
            account_id=account_id, fields=outcomes, error_code=code
        )

    async def subscribed_fields(
        self, account_id: str, token: SecretStr
    ) -> tuple[str, ...]:
        response = await self._call("GET", account_id, token)
        if not response.ok:
            raise ConnectionProviderError(
                "subscribed_apps read failed", response.error_code
            )
        fields: list[str] = []
        for app in response.body.get("data", []) or []:
            if not isinstance(app, dict):
                continue
            if self._app_id is None or str(app.get("id")) == self._app_id:
                for item in app.get("subscribed_fields", []) or []:
                    name = item.get("name") if isinstance(item, dict) else item
                    if isinstance(name, str):
                        fields.append(name)
        return tuple(fields)

    async def unsubscribe(self, account_id: str, token: SecretStr) -> bool:
        """``True`` only when Meta confirms ``{"success": true}``."""
        response = await self._call("DELETE", account_id, token)
        return _outcome(response) is FieldSubscriptionOutcome.SUBSCRIBED


# ── connector ────────────────────────────────────────────────────────────


class InstagramConnector(IInboxConnector):
    """Instagram professional accounts as Inboxes, via Meta Business Login."""

    def __init__(
        self,
        config: MetaLoginConfig,
        *,
        client_provider: Callable[[], httpx.AsyncClient],
        intent_store: IConnectionIntentStore,
        clock: Callable[[], float] = time.time,
        state_ttl_seconds: int = 600,
        subscription_fields: Sequence[str] = CORE_SUBSCRIPTION_FIELDS
        + COMMENT_SUBSCRIPTION_FIELDS,
        try_unverified_fields: Sequence[str] = UNVERIFIED_SUBSCRIPTION_FIELDS,
    ) -> None:
        self._login = MetaBusinessLogin(
            config,
            client_provider=client_provider,
            intent_store=intent_store,
            clock=clock,
            state_ttl_seconds=state_ttl_seconds,
        )
        self.subscriptions = InstagramSubscriptions(
            client_provider=client_provider,
            graph_base=config.graph_base,
            app_id=config.app_id,
        )
        self._fields = tuple(subscription_fields)
        self._unverified = tuple(try_unverified_fields)

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

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
        grant, _debug = await self._login.authorize(
            PlatformType.INSTAGRAM,
            state=state,
            host_subject=host_subject,
            code=code,
            error=error,
            error_reason=error_reason,
        )
        inboxes = tuple(
            DiscoveredInbox(
                inbox_ref=InboxRef(
                    platform=PlatformType.INSTAGRAM, inbox_id=account_id
                ),
                account_ref=PlatformAccountRef(
                    platform=PlatformType.INSTAGRAM, platform_account_id=account_id
                ),
                display_name=username,
                readiness=instagram_readiness(grant.scopes_for(account_id)),
            )
            for account_id, username in await self._assigned_accounts(
                grant.access_token
            )
        )
        return grant.model_copy(update={"inboxes": inboxes})

    async def _assigned_accounts(
        self, token: SecretStr
    ) -> list[tuple[str, str | None]]:
        found: list[tuple[str, str | None]] = []
        params: dict[str, Any] = {
            "fields": "id,username",
            "access_token": token.get_secret_value(),
            "limit": 100,
        }
        for _ in range(20):  # bounded pagination
            body = await self._login.get("me/assigned_instagram_accounts", params)
            for item in body.get("data", []) or []:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    found.append((item["id"], item.get("username")))
            paging = as_dict(body.get("paging"))
            after = as_dict(paging.get("cursors")).get("after")
            if not paging.get("next") or not isinstance(after, str):
                break
            params["after"] = after
        return found

    async def activate(
        self,
        grant: ConnectionGrant,
        inbox_ref: InboxRef,
        *,
        credentials: InboxCredentialService,
        previous: CredentialRecord | None = None,
    ) -> ActivationResult:
        """Subscribe the account's webhook fields, then build the encrypted record.

        The record is returned even when a field was refused, so the Host can
        decide; ``webhooks_subscribed`` reports the core conversation fields.
        """
        require_platform(self.platform, grant, inbox_ref)
        inbox = grant.inbox(inbox_ref)
        result = await self.subscriptions.subscribe(
            inbox_ref.inbox_id,
            grant.access_token,
            fields=self._fields,
            try_unverified=self._unverified,
        )
        return ActivationResult(
            inbox_ref=inbox_ref,
            record=build_record(
                credentials, inbox, grant.access_token, previous=previous
            ),
            webhooks_subscribed=result.core_subscribed,
            details={name: outcome.value for name, outcome in result.fields.items()},
            error_code=result.error_code,
        )

    async def disconnect(
        self, inbox_ref: InboxRef, account_ref: PlatformAccountRef, token: SecretStr
    ) -> bool:
        _ = account_ref  # the Instagram account is the Inbox itself
        return await self.subscriptions.unsubscribe(inbox_ref.inbox_id, token)


__all__ = [
    "COMMENT_SCOPES",
    "COMMENT_SUBSCRIPTION_FIELDS",
    "CORE_SUBSCRIPTION_FIELDS",
    "OPTIONAL_EXTENSION_SCOPES",
    "REQUIRED_CONVERSATION_SCOPES",
    "UNVERIFIED_SUBSCRIPTION_FIELDS",
    "FieldSubscriptionOutcome",
    "InstagramConnector",
    "InstagramSubscriptions",
    "SubscriptionResult",
    "instagram_readiness",
]
