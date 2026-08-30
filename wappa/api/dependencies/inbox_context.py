"""Inbox Execution Context for Inbox-dependent Wappa HTTP operations.

Wappa's own HTTP routes have no Meta payload to route from, so an authorized
caller selects the Inbox with ``X-Wappa-Inbox-ID``. The header selects
runtime scope and proves only that Wappa knows an active Inbox. It grants no
permission: Host authentication and authorization decide whether the caller
may operate that Inbox, and they run before this dependency.

The route already fixes the Platform (WhatsApp), so the header carries only
the native identifier. Resolution happens once per request and the result is
shared by every dependency in the route through FastAPI's dependency cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, Final

from fastapi import Header, HTTPException, Request

from wappa.core.logging.context import set_request_context
from wappa.core.logging.logger import get_logger
from wappa.domain.inbox.errors import (
    InboxCredentialIntegrityError,
    InboxDirectoryUnavailableError,
    InboxMutationConflictError,
    InboxNotFoundError,
)
from wappa.domain.inbox.identity import (
    InboxRef,
    PlatformAccountRef,
    validate_platform_native_id,
)
from wappa.domain.inbox.ports import ResolvedInboxCredentials
from wappa.domain.inbox.routing import InboxRoutingMode
from wappa.messaging.whatsapp.client.whatsapp_client import WhatsAppClient

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
    from wappa.messaging.template_transport import InboxTemplateTransport

INBOX_ID_HEADER: Final[str] = "X-Wappa-Inbox-ID"
INBOX_HEADER_DESCRIPTION: Final[str] = (
    "Selects the Inbox Execution Context for this operation. It proves only "
    "that Wappa knows an active Inbox; it is not a credential and grants no "
    "permission. Required in explicit mode; optional in legacy mode, where the "
    "configured single Inbox is the default."
)


@dataclass(frozen=True)
class InboxExecutionContext:
    """One validated, per-request bundle of Inbox capabilities.

    The decrypted token is held internally for client construction and is
    excluded from ``repr`` so it cannot leak through logging.
    """

    inbox_ref: InboxRef
    routing_mode: InboxRoutingMode
    session: httpx.AsyncClient
    media_download_client_provider: Any
    _credentials: ResolvedInboxCredentials = field(repr=False)

    @property
    def inbox_id(self) -> str:
        return self.inbox_ref.inbox_id

    @property
    def account_ref(self) -> PlatformAccountRef:
        return self._credentials.account_ref

    @property
    def platform_account_id(self) -> str:
        return self._credentials.platform_account_id

    def template_transport(self, app: FastAPI) -> InboxTemplateTransport:
        """Return this Inbox's Template transport, reusing resolved credentials.

        Routes call this instead of ``OutboundRuntime.from_app(app).templates(...)``
        so an Inbox-dependent request resolves the directory exactly once.
        """
        from wappa.messaging.template_transport import OutboundRuntime

        return OutboundRuntime.from_app(app).templates(
            self.inbox_id, credentials=self._credentials
        )

    def whatsapp_client(self) -> WhatsAppClient:
        """Build the WhatsApp client for this Inbox's credentials."""
        return WhatsAppClient(
            session=self.session,
            access_token=self._credentials.access_token.get_secret_value(),
            phone_number_id=self.inbox_id,
            logger=get_logger("wappa.api.whatsapp"),
        )


def _runtime(request: Request) -> InboxRuntimeConfiguration:
    runtime = getattr(request.app.state, "inbox_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Inbox routing is not configured; build the application through "
                "Wappa or WappaBuilder before serving Inbox-dependent routes"
            ),
        )
    return runtime  # type: ignore[no-any-return]


InboxIdHeader = Annotated[
    str | None,
    Header(
        alias=INBOX_ID_HEADER,
        description=INBOX_HEADER_DESCRIPTION,
        examples=["15551234567890"],
    ),
]
"""The declared header parameter.

Declaring it (rather than reading ``request.headers``) is what puts the
header, and the "selects scope, grants no permission" description, into the
OpenAPI schema of every Inbox-dependent route.
"""


def select_inbox_ref(request: Request, header_value: str | None = None) -> InboxRef:
    """Read the header (or the legacy default) without touching the directory.

    ``header_value`` comes from the declared header parameter. It falls back to
    reading the raw request headers so non-route callers keep working.
    """
    runtime = _runtime(request)
    raw = (
        header_value
        if header_value is not None
        else request.headers.get(INBOX_ID_HEADER)
    )
    if raw is not None and raw.strip():
        try:
            return InboxRef.whatsapp(
                validate_platform_native_id(raw.strip(), field_name=INBOX_ID_HEADER)
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid Inbox ID in {INBOX_ID_HEADER}: {exc}"
            ) from exc
    if runtime.default_inbox_ref is not None:
        return runtime.default_inbox_ref
    raise HTTPException(
        status_code=400,
        detail=(
            f"An explicit Inbox is required. Send it in the {INBOX_ID_HEADER} header."
        ),
    )


async def get_inbox_execution_context(
    request: Request,
    x_wappa_inbox_id: InboxIdHeader = None,
) -> InboxExecutionContext:
    """Resolve one Inbox Execution Context for an Inbox-dependent route.

    Order: Host auth already ran → read the header → combine with the route's
    Platform → legacy default when absent → resolve the active record once →
    build capabilities → bind logging context.

    Every Inbox-dependent route depends on this one callable, so FastAPI's
    dependency cache resolves it exactly once per request and documents the
    header once per route.
    """
    runtime = _runtime(request)
    inbox_ref = select_inbox_ref(request, x_wappa_inbox_id)

    try:
        credentials = await runtime.credential_resolver.resolve_credentials(inbox_ref)
    except InboxNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Unknown or inactive Inbox: {inbox_ref.inbox_id}"
        ) from exc
    except (
        InboxDirectoryUnavailableError,
        InboxCredentialIntegrityError,
        InboxMutationConflictError,
    ) as exc:
        get_logger(__name__).error(
            "Inbox Directory failure resolving %s: %s: %s",
            inbox_ref,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Inbox Directory is unavailable; cannot resolve the selected Inbox",
        ) from exc

    session_lifecycle = getattr(request.app.state, "session_lifecycle", None)
    if session_lifecycle is None:
        raise HTTPException(
            status_code=503,
            detail="SessionLifecycle is not available; Wappa startup is incomplete",
        )

    set_request_context(inbox_id=inbox_ref.inbox_id)
    return InboxExecutionContext(
        inbox_ref=inbox_ref,
        routing_mode=runtime.mode,
        session=session_lifecycle.get_session(),
        media_download_client_provider=session_lifecycle.get_media_download_client,
        _credentials=credentials,
    )


__all__ = [
    "INBOX_HEADER_DESCRIPTION",
    "INBOX_ID_HEADER",
    "InboxIdHeader",
    "InboxExecutionContext",
    "get_inbox_execution_context",
    "select_inbox_ref",
]
