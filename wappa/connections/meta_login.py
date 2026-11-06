"""Meta Business Login core shared by the WhatsApp and Instagram connectors.

Facebook Login for Business (a ``config_id``) drives both Meta Platforms:

1. Dialog: ``https://www.facebook.com/{v}/dialog/oauth?client_id&config_id
   &redirect_uri&response_type=code&state[&extras]``. WhatsApp Embedded Signup
   adds ``extras`` (for example ``{"sessionInfoVersion": "3"}``).
2. Code exchange: ``GET /{v}/oauth/access_token?client_id&client_secret
   [&redirect_uri]&code`` → Business Integration System User token. A code
   obtained through the JavaScript SDK popup (Embedded Signup) is exchanged
   without ``redirect_uri``; set ``redirect_uri=None`` for that flow.
3. Grants: ``GET /debug_token`` with the app token → scopes, granular targets.

Platform discovery and activation live in each connector.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from wappa.core.config.meta_application import (
    DEFAULT_GRAPH_API_VERSION,
    DEFAULT_GRAPH_BASE_URL,
)

from .contract import (
    AuthorizationRequest,
    ConnectionCancelledError,
    ConnectionIntent,
    ConnectionProviderError,
    ConnectionStateError,
    IConnectionIntentStore,
)


class MetaLoginConfig(BaseModel):
    """One Facebook Login for Business configuration (one per Platform flow)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    app_id: str = Field(min_length=1)
    app_secret: SecretStr
    config_id: str = Field(min_length=1)
    redirect_uri: str | None = None
    dialog_extras: dict[str, Any] | None = None
    graph_api_version: str = DEFAULT_GRAPH_API_VERSION
    graph_base_url: str = DEFAULT_GRAPH_BASE_URL
    dialog_base_url: str = "https://www.facebook.com"


def error_code(body: Any) -> str | None:
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or error.get("code") is None:
        return None
    sub = error.get("error_subcode")
    return f"{error['code']}/{sub}" if sub is not None else str(error["code"])


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class MetaBusinessLogin:
    """State binding, code exchange, scope evidence and Graph calls."""

    def __init__(
        self,
        config: MetaLoginConfig,
        *,
        client_provider: Callable[[], httpx.AsyncClient],
        intent_store: IConnectionIntentStore,
        clock: Callable[[], float] = time.time,
        state_ttl_seconds: int = 600,
    ) -> None:
        self.config = config
        self._client_provider = client_provider
        self._store = intent_store
        self._clock = clock
        self._ttl = state_ttl_seconds
        self._graph = f"{config.graph_base_url.rstrip('/')}/{config.graph_api_version}"

    # ── authorization ────────────────────────────────────────────────────

    async def begin(
        self, host_subject: str, *, metadata: dict[str, str] | None = None
    ) -> AuthorizationRequest:
        if not host_subject.strip():
            raise ValueError("host_subject must identify the authenticated operator")
        now = self._clock()
        intent = ConnectionIntent(
            state=secrets.token_urlsafe(32),
            host_subject=host_subject,
            created_at=now,
            expires_at=now + self._ttl,
            metadata=dict(metadata or {}),
        )
        await self._store.save(intent)
        query: dict[str, str] = {
            "client_id": self.config.app_id,
            "config_id": self.config.config_id,
            "response_type": "code",
            "state": intent.state,
        }
        if self.config.redirect_uri:
            query["redirect_uri"] = self.config.redirect_uri
        if self.config.dialog_extras:
            query["extras"] = json.dumps(self.config.dialog_extras)
        url = (
            f"{self.config.dialog_base_url.rstrip('/')}/"
            f"{self.config.graph_api_version}/dialog/oauth?{urlencode(query)}"
        )
        return AuthorizationRequest(
            url=url, state=intent.state, expires_at=intent.expires_at
        )

    async def consume(
        self,
        *,
        state: str | None,
        host_subject: str,
        code: str | None,
        error: str | None,
        error_reason: str | None,
    ) -> tuple[ConnectionIntent, str]:
        """Consume the one-use state first, so a replayed callback always fails."""
        if not state:
            raise ConnectionStateError("missing connection state")
        intent = await self._store.consume(state)
        if intent is None:
            raise ConnectionStateError("unknown or already used connection state")
        if self._clock() > intent.expires_at:
            raise ConnectionStateError("connection state expired")
        if not hmac.compare_digest(intent.host_subject, host_subject):
            raise ConnectionStateError(
                "connection state belongs to a different operator"
            )
        if error or not code:
            raise ConnectionCancelledError(
                f"authorization not completed ({error_reason or error or 'no code'})"
            )
        return intent, code.removesuffix("#_")

    async def exchange_code(self, code: str) -> tuple[SecretStr, int | None]:
        params = {
            "client_id": self.config.app_id,
            "client_secret": self.config.app_secret.get_secret_value(),
            "code": code,
        }
        if self.config.redirect_uri:
            params["redirect_uri"] = self.config.redirect_uri
        body = await self.get("oauth/access_token", params)
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise ConnectionProviderError("code exchange returned no access token")
        expires_in = body.get("expires_in")
        expires_at = (
            int(self._clock()) + expires_in
            if isinstance(expires_in, int) and expires_in > 0
            else None
        )
        return SecretStr(token), expires_at

    async def token_debug(self, token: SecretStr) -> dict[str, Any]:
        """``/debug_token`` data for a user/system-user token (app-token authed)."""
        app_token = f"{self.config.app_id}|{self.config.app_secret.get_secret_value()}"
        body = await self.get(
            "debug_token",
            {"input_token": token.get_secret_value(), "access_token": app_token},
        )
        data = as_dict(body.get("data"))
        if data.get("is_valid") is False:
            raise ConnectionProviderError("Meta reports the token as invalid", "190")
        return data

    @staticmethod
    def scopes_of(
        data: dict[str, Any],
    ) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
        scopes = tuple(s for s in data.get("scopes", []) or [] if isinstance(s, str))
        targets: dict[str, tuple[str, ...]] = {}
        for item in data.get("granular_scopes", []) or []:
            if isinstance(item, dict) and isinstance(item.get("scope"), str):
                ids = item.get("target_ids")
                if isinstance(ids, list):
                    targets[item["scope"]] = tuple(str(i) for i in ids)
        return scopes, targets

    # ── Graph transport ──────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        token: SecretStr | None = None,
    ) -> httpx.Response:
        headers = (
            {"Authorization": f"Bearer {token.get_secret_value()}"} if token else None
        )
        try:
            return await self._client_provider().request(
                method,
                f"{self._graph}/{path.lstrip('/')}",
                params=params,
                headers=headers,
                timeout=20.0,
            )
        except httpx.RequestError as exc:
            raise ConnectionProviderError(
                "Meta connection endpoint unreachable", "TRANSPORT"
            ) from exc

    async def get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        token: SecretStr | None = None,
    ) -> dict[str, Any]:
        response = await self._request("GET", path, params=params, token=token)
        try:
            body = response.json()
        except ValueError:
            body = None
        if not response.is_success or not isinstance(body, dict) or "error" in body:
            code = error_code(body) or str(response.status_code)
            raise ConnectionProviderError(f"Meta rejected {path.split('?')[0]}", code)
        return body

    async def success_call(
        self,
        method: str,
        path: str,
        token: SecretStr,
        params: dict[str, Any] | None = None,
    ) -> tuple[bool | None, str | None]:
        """``(True, None)`` on ``{"success": true}``; ``None`` = unknown outcome."""
        try:
            response = await self._request(method, path, params=params, token=token)
        except ConnectionProviderError:
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


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def parse_signed_request(signed_request: str, app_secret: SecretStr) -> dict[str, Any]:
    """Verify a Meta ``signed_request`` (deauthorize / data deletion callbacks)."""
    try:
        encoded_sig, payload = signed_request.split(".", 1)
        signature = _b64decode(encoded_sig)
        data = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ConnectionStateError("malformed signed_request") from exc
    if (
        not isinstance(data, dict)
        or str(data.get("algorithm", "")).upper() != "HMAC-SHA256"
    ):
        raise ConnectionStateError("unsupported signed_request algorithm")
    expected = hmac.new(
        app_secret.get_secret_value().encode(), payload.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise ConnectionStateError("signed_request signature mismatch")
    return data


__all__ = [
    "MetaBusinessLogin",
    "MetaLoginConfig",
    "as_dict",
    "error_code",
    "parse_signed_request",
]
