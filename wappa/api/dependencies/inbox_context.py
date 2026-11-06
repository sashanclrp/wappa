"""Inbox Execution Context for Inbox-dependent Wappa HTTP operations.

Wappa's own HTTP routes have no Meta payload to route from, so an authorized
caller selects the Inbox with ``X-Wappa-Inbox-ID``. The header selects
runtime scope and proves only that Wappa knows an active Inbox. It grants no
permission: Host authentication and authorization decide whether the caller
may operate that Inbox, and they run before this dependency.

The Platform comes from the route path (``/api/{platform}/...``; a route
without it is a wiring error), so the header carries only the native
identifier. Resolution happens once per request and the result is
shared by every dependency in the route through FastAPI's dependency cache.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Final

from fastapi import Depends, Header, HTTPException, Path, Request

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
from wappa.platforms import PLATFORMS
from wappa.schemas.core.types import PlatformType

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.core.factory.inbox_assembly import InboxRuntimeConfiguration
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.messaging.template_transport import InboxTemplateTransport

INBOX_ID_HEADER: Final[str] = "X-Wappa-Inbox-ID"
INBOX_HEADER_DESCRIPTION: Final[str] = (
    "Selects the Inbox Execution Context for this operation. It proves only "
    "that Wappa knows an active Inbox; it is not a credential and grants no "
    "permission. Required in explicit mode; optional in legacy mode, where the "
    "configured single Inbox is the default."
)


# The installed Platforms served by ``/api/{platform}``, derived from the
# Platform Registry so a new Platform needs no edit here.
RoutePlatform = StrEnum(  # type: ignore[misc]  # members come from PLATFORMS
    "RoutePlatform", {platform.name: platform.value for platform in PLATFORMS}
)


async def route_platform(
    platform: Annotated[
        RoutePlatform,
        Path(description="Platform of the Inbox: whatsapp or instagram"),
    ],
) -> RoutePlatform:
    """Router-level dependency: validates and documents ``{platform}``."""
    return platform


def _request_platform(request: Request) -> PlatformType:
    raw = request.path_params.get("platform")
    if raw is None:
        raise HTTPException(
            status_code=500,
            detail=(
                "Inbox-dependent route has no {platform} path parameter; mount it "
                "under /api/{platform}"
            ),
        )
    try:
        return PlatformType(RoutePlatform(raw).value)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Unsupported Platform: {raw}"
        ) from exc


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
    graph_api_version: str | None
    graph_base_url: str | None
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

    @property
    def credentials(self) -> ResolvedInboxCredentials:
        """The resolved credentials, for a Platform extension's own client.

        Only the WhatsApp extension router's dependencies read it; shared
        routes reach the Platform through the Messenger.
        """
        return self._credentials

    def template_transport(self, app: FastAPI) -> InboxTemplateTransport:
        """Return this Inbox's Template transport, reusing resolved credentials.

        Routes call this instead of ``OutboundRuntime.from_app(app).templates(...)``
        so an Inbox-dependent request resolves the directory exactly once.
        """
        from wappa.messaging.outbound_runtime import OutboundRuntime

        return OutboundRuntime.from_app(app).templates(
            self.inbox_ref, credentials=self._credentials
        )

    async def messenger(self, app: FastAPI) -> IMessenger:
        """This Inbox's Messenger for its own Platform, with app middleware.

        Built by ``OutboundRuntime`` (the same path as Host-initiated sends),
        reusing the credentials this request already resolved.
        """
        from wappa.messaging.outbound_runtime import OutboundRuntime

        return await OutboundRuntime.from_app(app).messenger(
            self.inbox_ref, credentials=self._credentials
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
    platform = _request_platform(request)
    raw = (
        header_value
        if header_value is not None
        else request.headers.get(INBOX_ID_HEADER)
    )
    if raw is not None and raw.strip():
        try:
            return InboxRef(
                platform=platform,
                inbox_id=validate_platform_native_id(
                    raw.strip(), field_name=INBOX_ID_HEADER
                ),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid Inbox ID in {INBOX_ID_HEADER}: {exc}"
            ) from exc
    default = runtime.default_inbox_ref
    if default is not None and default.platform is platform:
        return default
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
    meta_config = getattr(request.app.state, "meta_application_config", None)
    context = InboxExecutionContext(
        inbox_ref=inbox_ref,
        routing_mode=runtime.mode,
        session=session_lifecycle.get_session(),
        media_download_client_provider=session_lifecycle.get_media_download_client,
        graph_api_version=(
            meta_config.graph_api_version if meta_config is not None else None
        ),
        graph_base_url=(
            str(meta_config.graph_base_url) if meta_config is not None else None
        ),
        _credentials=credentials,
    )
    request.state.inbox_execution_context = context
    return context


async def get_inbox_messenger(
    request: Request,
    context: InboxExecutionContext = Depends(get_inbox_execution_context),
) -> IMessenger:
    """Messenger for the selected Inbox's Platform (send routes)."""
    return await context.messenger(request.app)


def requires_capability[C](kind: Callable[..., C]) -> Any:
    """Dependency: the selected Inbox's ``kind`` capability, or 501.

    Routes gate on what the Inbox's Messenger can do, never on the Platform
    name (ADR-0016, ADR-0021), so a Platform that gains the capability serves
    the route without changes.
    """

    async def dependency(
        request: Request,
        context: InboxExecutionContext = Depends(get_inbox_execution_context),
    ) -> C:
        messenger = await context.messenger(request.app)
        found = messenger.capability(kind)
        if found is None:
            raise HTTPException(
                status_code=501,
                detail=(
                    f"{context.inbox_ref.platform.value} does not provide "
                    f"{getattr(kind, '__name__', kind)}"
                ),
            )
        return found

    return dependency


__all__ = [
    "INBOX_HEADER_DESCRIPTION",
    "INBOX_ID_HEADER",
    "InboxIdHeader",
    "InboxExecutionContext",
    "RoutePlatform",
    "get_inbox_execution_context",
    "get_inbox_messenger",
    "requires_capability",
    "route_platform",
    "select_inbox_ref",
]
