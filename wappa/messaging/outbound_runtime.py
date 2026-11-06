"""The outbound Messenger factory every Platform's sends go through.

``OutboundRuntime`` resolves Inbox credentials and Wappa's live HTTP clients,
builds the Inbox's Messenger Adapter and wraps it in the app's Messenger
Pipeline. Host-initiated sends, the Messaging HTTP API and the Template
transport all start here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, cast

from wappa.core.messaging.pipeline import MessengerPipeline, MiddlewareEntry
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import (
    IInboxCredentialResolver,
    ResolvedInboxCredentials,
)
from wappa.messaging.template_transport import InboxTemplateTransport

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.domain.factories import MessengerFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.platforms import PlatformEntry
    from wappa.schemas.core.types import PlatformType


class OutboundRuntime:
    """Build Inbox-scoped outbound capabilities from Wappa-owned resources."""

    def __init__(
        self,
        *,
        session_provider: Callable[[], httpx.AsyncClient],
        media_download_client_provider: Callable[[], httpx.AsyncClient],
        credential_resolver: IInboxCredentialResolver,
        messenger_middleware: Sequence[MiddlewareEntry] = (),
        graph_api_version: str | None = None,
        graph_base_url: str | None = None,
        platforms: Mapping[PlatformType, PlatformEntry] | None = None,
    ) -> None:
        # Local import prevents the public ``wappa.messaging`` package from
        # cycling while MessengerFactory imports its WhatsApp adapter modules.
        from wappa.domain.factories import MessengerFactory

        self._messenger_factory: MessengerFactory = MessengerFactory(
            session_provider=session_provider,
            credential_resolver=credential_resolver,
            media_download_client_provider=media_download_client_provider,
            graph_api_version=graph_api_version,
            graph_base_url=graph_base_url,
            platforms=platforms,
        )
        self._messenger_middleware = tuple(messenger_middleware)
        self._platforms = platforms

    @classmethod
    def from_app(cls, app: FastAPI) -> OutboundRuntime:
        """Resolve Wappa's active resources from a configured FastAPI app."""
        existing = getattr(app.state, "outbound_runtime", None)
        if isinstance(existing, cls):
            return existing

        lifecycle = getattr(app.state, "session_lifecycle", None)
        if lifecycle is None:
            raise RuntimeError(
                "SessionLifecycle is not available; Wappa startup is incomplete"
            )
        inbox_runtime = getattr(app.state, "inbox_runtime", None)
        if inbox_runtime is None:
            raise RuntimeError("Inbox routing is not configured on this application")

        runtime = cls(
            session_provider=lifecycle.get_session,
            credential_resolver=cast(
                IInboxCredentialResolver, inbox_runtime.credential_resolver
            ),
            messenger_middleware=getattr(app.state, "messenger_middleware", ()),
            media_download_client_provider=lifecycle.get_media_download_client,
            graph_api_version=(
                app.state.meta_application_config.graph_api_version
                if getattr(app.state, "meta_application_config", None) is not None
                else None
            ),
            graph_base_url=(
                str(app.state.meta_application_config.graph_base_url)
                if getattr(app.state, "meta_application_config", None) is not None
                else None
            ),
            platforms=getattr(app.state, "platforms", None),
        )
        app.state.outbound_runtime = runtime
        return runtime

    def templates(
        self,
        inbox_ref: InboxRef,
        *,
        credentials: ResolvedInboxCredentials | None = None,
    ) -> InboxTemplateTransport:
        """Return a Template transport capability scoped to ``inbox_ref``.

        ``credentials`` lets a caller that already resolved this Inbox — an
        HTTP route holding an ``InboxExecutionContext`` — hand the resolved
        record over instead of making the directory answer twice. A send on an
        Inbox whose Messenger has no ``ITemplateMessaging`` is REJECTED with
        ``capability_unsupported`` before any I/O.
        """
        return InboxTemplateTransport(
            inbox_ref=inbox_ref,
            messenger_provider=lambda: self.messenger(
                inbox_ref, credentials=credentials
            ),
        )

    async def messenger(
        self,
        inbox_ref: InboxRef,
        *,
        credentials: ResolvedInboxCredentials | None = None,
    ) -> IMessenger:
        """Inbox-bound Messenger (with app middleware) for Host-initiated sends.

        Use it for agent replies, delayed jobs or human-takeover sends outside
        a webhook dispatch. The Host authorizes the caller and enforces its own
        takeover/pause policy before sending.
        """
        raw = await self._messenger_factory.create_messenger(
            inbox_ref, credentials=credentials
        )
        return MessengerPipeline(raw=raw, middleware=self._messenger_middleware)

    async def platform_messenger(
        self,
        inbox_ref: InboxRef,
        *,
        credentials: ResolvedInboxCredentials | None = None,
    ) -> IMessenger | None:
        """The Inbox's Platform Messenger, outside a dispatch.

        The same object a handler gets as ``self.whatsapp`` or
        ``self.instagram``, built over :meth:`messenger` so middleware runs.
        ``None`` when the Inbox's Platform adds no Platform Messenger. Hosts
        narrow it with ``isinstance(m, WhatsAppMessenger)`` (or the Instagram
        type) before using Platform methods.
        """
        from wappa.platforms import platform_messenger

        return platform_messenger(
            await self.messenger(inbox_ref, credentials=credentials),
            self._platforms,
        )

    def evict_inbox(self, inbox_ref: InboxRef) -> None:
        """Drop the cached Messenger for one Inbox.

        The Inbox Directory evicts automatically after ``refresh_inbox`` and
        ``deactivate_inbox``; this hook exists for hosts that rotate a token
        out of band.
        """
        self._messenger_factory.evict(inbox_ref)
