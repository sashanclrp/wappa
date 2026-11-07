"""Shared construction of Dispatch Context capabilities.

Webhook intake, API-message events, Scheduled Tasks, and External Webhook Sources
all bind a ``WappaEventHandler`` clone to Inbox and User identity plus the
runtime capabilities the path needs. This module is the one place that
knows how to turn qualified Inbox identity into a Messenger, a Cache
Factory, and the optional ``db`` / ``db_read`` session factories.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any

from wappa.core.logging.context import (
    bind_inbox_context,
    bind_user_context,
    reset_inbox_context,
    reset_user_context,
)
from wappa.core.messaging.deferred import DeferredMessenger
from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.core.messaging.sent_message_registry import TableSentMessageRegistry
from wappa.core.sse.context import sse_event_scope, sse_identity_cleared
from wappa.domain.factories.messenger_factory import MessengerFactory
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.domain.interfaces.sent_message_registry import ISentMessageRegistry
from wappa.persistence.cache_factory import create_cache_factory

# Table Cache ignores the User; any non-empty placeholder satisfies the factory.
_REGISTRY_USER = "__sent_registry__"

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.core.config.meta_application import MetaApplicationConfig
    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.identity_resolver import IIdentityResolver
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.platforms import PlatformEntry
    from wappa.schemas.core.types import PlatformType

SessionFactory = Callable[[], Any]


def resolve_database_factories(
    postgres_session_manager: Any | None,
) -> tuple[SessionFactory | None, SessionFactory | None]:
    """``(db, db_read)`` for a session manager, or ``(None, None)``.

    Every dispatch path — webhook, API message, scheduled, External Webhook Source —
    derives its optional session factories here. Wappa never installs a fake
    session factory in place of ``None``.
    """
    if postgres_session_manager is None:
        return None, None
    return (
        postgres_session_manager.get_session,
        postgres_session_manager.get_read_session,
    )


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Application-level resources a Dispatch Context can draw on."""

    session_provider: Callable[[], httpx.AsyncClient]
    media_download_client_provider: Callable[[], httpx.AsyncClient]
    credential_resolver: IInboxCredentialResolver
    messenger_middleware: Sequence[Any]
    cache_type: str
    background_work_tracker: Any
    meta_application_config: MetaApplicationConfig | None = None
    redis_manager: Any | None = None
    postgres_session_manager: Any | None = None
    identity_resolver: IIdentityResolver | None = None
    platforms: Mapping[PlatformType, PlatformEntry] = field(
        default_factory=lambda: _default_platforms()
    )

    @classmethod
    def from_app(cls, app: FastAPI) -> RuntimeCapabilities:
        state = app.state
        session_lifecycle = getattr(state, "session_lifecycle", None)
        if session_lifecycle is None:
            raise RuntimeError(
                "app.state.session_lifecycle is not set — WappaCorePlugin must "
                "run startup before Dispatch Contexts can be built"
            )
        runtime = getattr(state, "inbox_runtime", None)
        if runtime is None:
            raise RuntimeError(
                "app.state.inbox_runtime is not set — build the application "
                "through Wappa or WappaBuilder so an Inbox Routing Mode is assembled"
            )
        return cls(
            session_provider=session_lifecycle.get_session,
            media_download_client_provider=session_lifecycle.get_media_download_client,
            credential_resolver=runtime.credential_resolver,
            messenger_middleware=getattr(state, "messenger_middleware", ()),
            cache_type=getattr(state, "wappa_cache_type", "memory"),
            background_work_tracker=getattr(state, "background_work_tracker", None),
            meta_application_config=getattr(state, "meta_application_config", None),
            redis_manager=getattr(state, "redis_manager", None),
            postgres_session_manager=getattr(state, "postgres_session_manager", None),
            identity_resolver=getattr(state, "identity_resolver", None),
            platforms=getattr(state, "platforms", None) or _default_platforms(),
        )


def _default_platforms() -> Mapping[PlatformType, PlatformEntry]:
    # Imported here: the Platform Registry imports the inbound adapters,
    # whose package imports this module.
    from wappa.platforms import PLATFORMS

    return PLATFORMS


class DispatchContextBuilder:
    """Build the capabilities one Dispatch Context needs."""

    def __init__(self, capabilities: RuntimeCapabilities) -> None:
        self.capabilities = capabilities
        self.sent_message_registry: ISentMessageRegistry = TableSentMessageRegistry(
            lambda ref: self.cache_factory(ref, _REGISTRY_USER).create_table_cache()
        )
        self._messenger_factory = MessengerFactory(
            sent_registry=self.sent_message_registry,
            platforms=capabilities.platforms,
            session_provider=capabilities.session_provider,
            media_download_client_provider=capabilities.media_download_client_provider,
            credential_resolver=capabilities.credential_resolver,
            graph_api_version=(
                capabilities.meta_application_config.graph_api_version
                if capabilities.meta_application_config is not None
                else None
            ),
            graph_base_url=(
                str(capabilities.meta_application_config.graph_base_url)
                if capabilities.meta_application_config is not None
                else None
            ),
        )

    @classmethod
    def from_app(cls, app: FastAPI) -> DispatchContextBuilder:
        existing = getattr(app.state, "dispatch_context_builder", None)
        if isinstance(existing, cls):
            return existing
        builder = cls(RuntimeCapabilities.from_app(app))
        app.state.dispatch_context_builder = builder
        return builder

    @property
    def messenger_factory(self) -> MessengerFactory:
        return self._messenger_factory

    async def messenger(
        self,
        inbox_ref: InboxRef,
        *,
        credentials: ResolvedInboxCredentials | None = None,
    ) -> IMessenger:
        """Return the pipeline-wrapped Messenger for ``inbox_ref``.

        Directory failures propagate as their typed categories.
        """
        raw = await self._messenger_factory.create_messenger(
            inbox_ref, credentials=credentials
        )
        return MessengerPipeline(
            raw=raw, middleware=self.capabilities.messenger_middleware
        )

    def cache_factory(self, inbox_ref: InboxRef, user_id: str) -> ICacheFactory:
        cache_type = self.capabilities.cache_type
        if cache_type == "redis":
            redis_manager = self.capabilities.redis_manager
            if redis_manager is None:
                raise RuntimeError(
                    "Redis cache requested but RedisPlugin not available. "
                    "Ensure Wappa(cache='redis') is used or RedisPlugin is added manually."
                )
            if not redis_manager.is_initialized():
                raise RuntimeError(
                    "Redis cache requested but RedisManager not initialized. "
                    "Check Redis server connectivity and startup logs."
                )
        factory_class = create_cache_factory(cache_type)
        return factory_class(inbox_id=inbox_ref.cache_namespace, user_id=user_id)

    def database_factories(self) -> tuple[SessionFactory | None, SessionFactory | None]:
        """``(db, db_read)``: optional, never a fake session factory."""
        return resolve_database_factories(self.capabilities.postgres_session_manager)

    def bind_handler(
        self,
        base_handler: WappaEventHandler,
        *,
        inbox_ref: InboxRef | None,
        user_id: str | None,
        messenger: IMessenger | None,
        cache_factory: ICacheFactory | None,
    ) -> WappaEventHandler:
        db, db_read = self.database_factories()
        handler = base_handler.with_context(
            inbox_id=inbox_ref.inbox_id if inbox_ref is not None else None,
            inbox_ref=inbox_ref,
            user_id=user_id,
            messenger=messenger,
            cache_factory=cache_factory,
            db=db,
            db_read=db_read,
            platforms=self.capabilities.platforms,
        )
        # ``self.scope(...)`` clones the prototype again, never this clone, so
        # state a Host set during one dispatch cannot leak into another subject.
        handler._scope_opener = partial(self.scope, base_handler)
        return handler

    async def canonical_user(self, inbox_ref: InboxRef, subject: str) -> str:
        """Ask the Host resolver for the canonical User of ``subject``.

        Resolver failures propagate: acting under a guessed User would read and
        write the wrong cache.
        """
        resolver = self.capabilities.identity_resolver
        if resolver is None:
            return subject
        canonical = await resolver.resolve(subject, inbox_ref=inbox_ref)
        if not canonical:
            raise ValueError(
                f"Identity resolver returned no User for a subject in {inbox_ref}"
            )
        return canonical

    @asynccontextmanager
    async def scope(
        self,
        base_handler: WappaEventHandler,
        *,
        inbox_ref: InboxRef | None,
        user_id: str | None,
    ) -> AsyncIterator[WappaEventHandler]:
        """Yield a fresh handler bound to one explicit scope.

        +----------------+--------------------------------------------------+
        | Inbox and User | canonical User, deferred Messenger, caches, db   |
        | Inbox only     | deferred Messenger, db; no User or Cache Factory |
        | System         | db; no invented Inbox, Messenger or User         |
        +----------------+--------------------------------------------------+

        Inbox-bound scopes offer a Messenger without resolving credentials.
        Credential failures surface on its first operation; failed resolution
        is retried on the next use. Other required capabilities that cannot be
        built raise before the body runs.
        SSE and log identity hold for the body and are restored on exit, so a
        nested scope never leaks into its parent or into concurrent work.
        """
        if inbox_ref is None:
            if user_id is not None:
                raise ValueError("A User-scoped context requires inbox_ref")
            handler = self.bind_handler(
                base_handler,
                inbox_ref=None,
                user_id=None,
                messenger=None,
                cache_factory=None,
            )
            with _log_identity(None, None), sse_identity_cleared():
                yield handler
            return

        canonical = (
            await self.canonical_user(inbox_ref, user_id)
            if user_id is not None
            else None
        )
        with _log_identity(inbox_ref.inbox_id, canonical):
            entry = self.capabilities.platforms.get(inbox_ref.platform)
            if entry is None:
                raise ValueError(f"Unsupported platform: {inbox_ref.platform.value}")
            messenger = DeferredMessenger(
                inbox_ref,
                partial(self.messenger, inbox_ref),
                supported_operations=entry.messenger_operations,
                capability_types=entry.messenger_capabilities,
            )
            cache_factory = (
                self.cache_factory(inbox_ref, canonical)
                if canonical is not None
                else None
            )
            handler = self.bind_handler(
                base_handler,
                inbox_ref=inbox_ref,
                user_id=canonical,
                messenger=messenger,
                cache_factory=cache_factory,
            )
            async with sse_event_scope(
                inbox_id=inbox_ref.inbox_id,
                user_id=canonical or "unknown",
                platform=inbox_ref.platform.value,
                tracker=self.capabilities.background_work_tracker,
            ):
                yield handler


@contextmanager
def _log_identity(inbox_id: str | None, user_id: str | None) -> Iterator[None]:
    inbox_token = bind_inbox_context(inbox_id)
    user_token = bind_user_context(user_id)
    try:
        yield
    finally:
        reset_user_context(user_token)
        reset_inbox_context(inbox_token)


__all__ = [
    "DispatchContextBuilder",
    "RuntimeCapabilities",
    "resolve_database_factories",
]
