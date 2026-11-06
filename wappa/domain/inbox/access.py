"""Supported trusted-adapter access to an Inbox's *current* credentials.

ADR-0025: a trusted backend extension (publishing, analytics, …) may receive
the active bearer for one Inbox through this narrow seam instead of importing
Wappa's internal resolver or decrypting records itself.

Rules:

- The Host authorizes the caller first; knowing an Inbox ID grants nothing.
- Resolve per operation; never cache the returned value as a permanent
  snapshot. Rotation/deactivation affects the *next* resolution only.
- Keep the value in trusted server-side code: never AI tool arguments,
  browser responses, logs or durable plaintext.
- Unknown/inactive/integrity/unavailable outcomes raise the Inbox Directory's
  typed errors unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr

from wappa.core.config.meta_application import (
    DEFAULT_GRAPH_API_VERSION,
    DEFAULT_GRAPH_BASE_URL,
)
from wappa.domain.inbox.identity import InboxRef, PlatformAccountRef
from wappa.domain.inbox.ports import IInboxCredentialResolver


@dataclass(frozen=True, slots=True, repr=False)
class TrustedInboxCredential:
    inbox_ref: InboxRef
    account_ref: PlatformAccountRef
    access_token: SecretStr
    credential_version: int
    graph_api_version: str
    graph_base_url: str

    def __repr__(self) -> str:
        return (
            f"TrustedInboxCredential(inbox_ref={self.inbox_ref!s}, "
            f"credential_version={self.credential_version}, access_token=**********)"
        )

    def authorization_header(self) -> dict[str, str]:
        """Bearer header for the trusted adapter's own provider client."""
        return {"Authorization": f"Bearer {self.access_token.get_secret_value()}"}


class InboxCredentialAccess:
    """Resolve the active credential/version of one qualified Inbox."""

    def __init__(
        self,
        resolver: IInboxCredentialResolver,
        *,
        graph_api_version: str = DEFAULT_GRAPH_API_VERSION,
        graph_base_url: str = DEFAULT_GRAPH_BASE_URL,
    ) -> None:
        self._resolver = resolver
        self._version = graph_api_version
        self._base = graph_base_url.rstrip("/")

    @classmethod
    def from_app(cls, app: Any) -> InboxCredentialAccess:
        """Build from a started Wappa FastAPI app (``wappa.asgi``)."""
        inbox_runtime = getattr(app.state, "inbox_runtime", None)
        if inbox_runtime is None:
            raise RuntimeError("Inbox routing is not configured on this application")
        config = getattr(app.state, "meta_application_config", None)
        kwargs: dict[str, str] = {}
        if config is not None:
            kwargs = {
                "graph_api_version": config.graph_api_version,
                "graph_base_url": str(config.graph_base_url),
            }
        return cls(inbox_runtime.credential_resolver, **kwargs)

    async def resolve(self, inbox_ref: InboxRef) -> TrustedInboxCredential:
        resolved = await self._resolver.resolve_credentials(inbox_ref)
        if resolved.inbox_ref != inbox_ref:
            raise ValueError("credential resolver returned a different Inbox")
        return TrustedInboxCredential(
            inbox_ref=resolved.inbox_ref,
            account_ref=resolved.account_ref,
            access_token=resolved.access_token,
            credential_version=resolved.credential_version,
            graph_api_version=self._version,
            graph_base_url=self._base,
        )


__all__ = ["InboxCredentialAccess", "TrustedInboxCredential"]
