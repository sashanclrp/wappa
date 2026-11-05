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
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

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
)
from .meta_login import MetaBusinessLogin, MetaLoginConfig, as_dict, error_code

if TYPE_CHECKING:
    from wappa.webhooks.core.webhook_interfaces import InboxConnectionWebhook

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


def _outcome(ok: bool | None) -> FieldSubscriptionOutcome:
    if ok:
        return FieldSubscriptionOutcome.SUBSCRIBED
    return (
        FieldSubscriptionOutcome.UNKNOWN
        if ok is None
        else FieldSubscriptionOutcome.REJECTED
    )


class InstagramSubscriptions:
    """Account-level webhook field subscription (``/{ig-id}/subscribed_apps``)."""

    def __init__(
        self,
        *,
        client_provider: Callable[[], httpx.AsyncClient],
        graph_api_version: str = "v26.0",
        graph_base_url: str = "https://graph.facebook.com",
        app_id: str | None = None,
    ) -> None:
        self._client_provider = client_provider
        self._graph = f"{graph_base_url.rstrip('/')}/{graph_api_version}"
        self._app_id = app_id

    async def _subscribe_call(
        self, account_id: str, token: SecretStr, fields: Sequence[str]
    ) -> tuple[bool | None, str | None]:
        try:
            response = await self._client_provider().post(
                f"{self._graph}/{account_id}/subscribed_apps",
                params={"subscribed_fields": ",".join(fields)},
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                timeout=20.0,
            )
        except httpx.RequestError:
            return None, "TRANSPORT"
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.is_success and as_dict(body).get("success") is True:
            return True, None
        if response.status_code >= 500 or response.is_success:
            return None, "INDETERMINATE"
        return False, error_code(body) or str(response.status_code)

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
        outcomes: dict[str, FieldSubscriptionOutcome] = {}
        ok, code = await self._subscribe_call(account_id, token, fields)
        outcomes.update(dict.fromkeys(fields, _outcome(ok)))
        if ok and try_unverified:
            extra_ok, _ = await self._subscribe_call(
                account_id, token, [*fields, *try_unverified]
            )
            outcomes.update(dict.fromkeys(try_unverified, _outcome(extra_ok)))
            if not extra_ok:
                # Restore the verified set if the combined call failed.
                await self._subscribe_call(account_id, token, fields)
        return SubscriptionResult(
            account_id=account_id, fields=outcomes, error_code=code
        )

    async def subscribed_fields(
        self, account_id: str, token: SecretStr
    ) -> tuple[str, ...]:
        try:
            response = await self._client_provider().get(
                f"{self._graph}/{account_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                timeout=20.0,
            )
            body = response.json()
        except (httpx.RequestError, ValueError) as exc:
            raise ConnectionProviderError(
                "subscribed_apps unreachable", "TRANSPORT"
            ) from exc
        if not response.is_success or not isinstance(body, dict):
            raise ConnectionProviderError(
                "Meta rejected subscribed_apps read",
                error_code(body) or str(response.status_code),
            )
        fields: list[str] = []
        for app in body.get("data", []) or []:
            if not isinstance(app, dict):
                continue
            if self._app_id is None or str(app.get("id")) == self._app_id:
                for item in app.get("subscribed_fields", []) or []:
                    name = item.get("name") if isinstance(item, dict) else item
                    if isinstance(name, str):
                        fields.append(name)
        return tuple(fields)

    async def unsubscribe(self, account_id: str, token: SecretStr) -> bool:
        try:
            response = await self._client_provider().delete(
                f"{self._graph}/{account_id}/subscribed_apps",
                headers={"Authorization": f"Bearer {token.get_secret_value()}"},
                timeout=20.0,
            )
        except httpx.RequestError:
            return False
        try:
            return bool(response.is_success and response.json().get("success") is True)
        except ValueError:
            return False


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
            graph_api_version=config.graph_api_version,
            graph_base_url=config.graph_base_url,
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
        intent, code = await self._login.consume(
            state=state,
            host_subject=host_subject,
            code=code,
            error=error,
            error_reason=error_reason,
        )
        token, expires_at = await self._login.exchange_code(code)
        scopes, targets = MetaBusinessLogin.scopes_of(
            await self._login.token_debug(token)
        )
        grant = ConnectionGrant(
            platform=PlatformType.INSTAGRAM,
            intent_subject=intent.host_subject,
            access_token=token,
            inboxes=(),
            granted_scopes=scopes,
            scope_targets=targets,
            expires_at=expires_at,
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
            for account_id, username in await self._assigned_accounts(token)
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
        previous: Any | None = None,
    ) -> ActivationResult:
        """Subscribe the account's webhook fields, then build the encrypted record.

        The record is returned even when a field was refused, so the Host can
        decide; ``webhooks_subscribed`` reports the core conversation fields.
        """
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


def deauthorization_event(
    signed_request: str, app_secret: SecretStr
) -> InboxConnectionWebhook:
    """Verify Meta's Instagram deauthorize callback → ``InboxConnectionWebhook``.

    Meta POSTs a ``signed_request`` form field when an account removes the
    app. The verified ``user_id`` is the Instagram account (the Inbox), so the
    same ``InboxConnectionWebhook(DISCONNECTED)`` a WhatsApp
    ``account_offboarded`` produces reaches ``process_inbox_connection``
    (ADR-0016). Raises ``ConnectionStateError`` on a bad signature.
    """
    from datetime import UTC, datetime

    from wappa.webhooks.core.webhook_interfaces import (
        InboxBase,
        InboxConnectionState,
        InboxConnectionWebhook,
    )

    from .contract import ConnectionStateError
    from .meta_login import parse_signed_request

    data = parse_signed_request(signed_request, app_secret)
    account_id = str(data.get("user_id") or "")
    if not account_id:
        raise ConnectionStateError("signed_request carries no user_id")
    issued = data.get("issued_at")
    when = (
        datetime.fromtimestamp(issued, tz=UTC)
        if isinstance(issued, int)
        else datetime.now(UTC)
    )
    return InboxConnectionWebhook(
        inbox=InboxBase(
            inbox_id=account_id, display_address=None, platform_account_id=account_id
        ),
        state=InboxConnectionState.DISCONNECTED,
        reason="app_deauthorized",
        account_id=account_id,
        timestamp=when,
        platform=PlatformType.INSTAGRAM,
        webhook_id=f"deauthorize:{account_id}:{int(when.timestamp())}",
    )


__all__ = [
    "deauthorization_event",
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
