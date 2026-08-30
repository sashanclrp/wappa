"""Shared construction of Dispatch Context capabilities.

Webhook intake, API-message events, cron jobs, and External Webhook Sources
all bind a ``WappaEventHandler`` clone to Inbox and User identity plus the
runtime capabilities the path needs. This module is the one place that
knows how to turn qualified Inbox identity into a Messenger, a Cache
Factory, and the optional ``db`` / ``db_read`` session factories.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wappa.core.messaging.pipeline import MessengerPipeline
from wappa.domain.factories.messenger_factory import MessengerFactory
from wappa.domain.inbox.identity import InboxRef
from wappa.domain.inbox.ports import IInboxCredentialResolver, ResolvedInboxCredentials
from wappa.persistence.cache_factory import create_cache_factory

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

    from wappa.core.events.event_handler import WappaEventHandler
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger

SessionFactory = Callable[[], Any]


def resolve_database_factories(
    postgres_session_manager: Any | None,
) -> tuple[SessionFactory | None, SessionFactory | None]:
    """``(db, db_read)`` for a session manager, or ``(None, None)``.

    Every dispatch path — webhook, API message, cron, External Webhook Source —
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
    redis_manager: Any | None = None
    postgres_session_manager: Any | None = None

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
            redis_manager=getattr(state, "redis_manager", None),
            postgres_session_manager=getattr(state, "postgres_session_manager", None),
        )


class DispatchContextBuilder:
    """Build the capabilities one Dispatch Context needs."""

    def __init__(self, capabilities: RuntimeCapabilities) -> None:
        self.capabilities = capabilities
        self._messenger_factory = MessengerFactory(
            session_provider=capabilities.session_provider,
            media_download_client_provider=capabilities.media_download_client_provider,
            credential_resolver=capabilities.credential_resolver,
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
        user_id: str,
        messenger: IMessenger | None,
        cache_factory: ICacheFactory | None,
    ) -> WappaEventHandler:
        db, db_read = self.database_factories()
        return base_handler.with_context(
            inbox_id=inbox_ref.inbox_id if inbox_ref is not None else "",
            user_id=user_id,
            messenger=messenger,
            cache_factory=cache_factory,
            db=db,
            db_read=db_read,
        )


__all__ = [
    "DispatchContextBuilder",
    "RuntimeCapabilities",
    "resolve_database_factories",
]
