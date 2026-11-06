"""
Base event handler class for Wappa applications.

This provides the interface that developers implement to handle WhatsApp webhooks.
"""

from __future__ import annotations

import copy
from abc import ABC
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Self

from ..default_handlers import (
    DefaultConversationEventHandler,
    DefaultErrorHandler,
    DefaultMessageHandler,
    DefaultStatusHandler,
    DefaultSystemHandler,
)
from ._api_lane import _ApiLane
from ._diagnostics import _Diagnostics
from ._external_lane import _ExternalLane
from ._scheduled_lane import _ScheduledLane
from ._webhook_lanes import _WebhookLanes

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.domain.inbox.identity import InboxRef
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.platforms import PlatformEntry
    from wappa.schemas.core.types import PlatformType


class WappaEventHandler(
    _WebhookLanes, _ApiLane, _ExternalLane, _ScheduledLane, _Diagnostics, ABC
):
    """
    Base class for handling WhatsApp events in Wappa applications.

    Developers inherit from this class and implement the handler methods
    to define their application's behavior for different webhook events.

    Dependencies are injected PER-REQUEST via with_context() method:
    - inbox_id: Inbox identifier for this request's context
    - user_id: User identifier for this request's context
    - messenger: IMessenger created with correct inbox_id for each request
    - whatsapp / instagram: the Platform Messenger for this dispatch's Platform,
      ready to call (``self.whatsapp.templates``, ``self.instagram.comments``);
      the other is ``None``
    - cache_factory: Cache factory for inbox-specific data persistence
    - db: Database session factory for write operations (PostgresDatabasePlugin)
    - db_read: Database session factory for read operations (uses replicas if configured)

    IMPORTANT: Each request gets a FRESH handler instance via with_context() to ensure
    thread safety. The base handler acts as a prototype that is cloned per-request.

    This ensures proper multi-inbox support where each webhook is processed
    with the correct inbox-specific context and dependencies.

    Database Availability Across Handler Methods:
        All handler methods have access to self.db when PostgresDatabasePlugin is configured:
        - process_message(): Webhook handler - self.db always available
        - process_status(): Webhook handler - self.db always available
        - process_error(): Webhook handler - self.db always available
        - process_api_message(): API event handler - self.db available when FastAPI Request
                                 is passed to the dispatcher (see note below)
        - process_scheduled_event(): Scheduled lane - self.db always available

        Note for process_api_message():
            For self.db to be available in process_api_message(), API routes must pass
            the FastAPI Request object to the event dispatch functions. Example:

            # Using dispatch_api_message_event:
            await dispatch_api_message_event(
                dispatcher, message_type, result, payload, recipient,
                request=fastapi_request  # Pass Request for DB access
            )

            # Using fire_api_event:
            fire_api_event(
                dispatcher, message_type, result, payload, recipient,
                fastapi_request=request  # Pass Request for DB access
            )

            # Using @dispatch_message_event decorator:
            @dispatch_message_event("text")
            async def send_text(
                request: TextMessage,
                fastapi_request: Request,  # Include Request parameter
                api_dispatcher: APIEventDispatcher = Depends(get_api_event_dispatcher),
            ):
                ...

    Database Usage:
        async with self.db() as session:
            user = await session.exec(select(User).where(User.phone == phone))
            # Auto-commits on context exit if auto_commit=True

        # For read-heavy operations (uses replicas if configured):
        async with self.db_read() as session:
            results = await session.exec(select(User))
    """

    def __init__(self) -> None:
        """Initialize event handler as a prototype (dependencies injected via with_context)."""
        # Per-request context (set via with_context() - NOT mutable on prototype)
        self.inbox_id: str | None = None
        self.inbox_ref: InboxRef | None = None
        self.user_id: str | None = None

        # Per-request dependencies (set via with_context() - NOT mutable on prototype)
        self.messenger: IMessenger | None = None
        # The Platform Messenger for the dispatch's Platform: ``self.messenger``
        # plus that Platform's ready capabilities. Exactly one is set when a
        # Messenger is bound; both stay None otherwise (ADR-0025 rule 12).
        self.whatsapp = None
        self.instagram = None
        self.cache_factory: ICacheFactory | None = None

        # Database session factories (set via with_context())
        # Usage: async with self.db() as session: ...
        self.db: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None
        self.db_read: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = (
            None
        )

        # Opens ``self.scope(...)``; bound by the Dispatch Context builder.
        self._scope_opener: Callable[..., AbstractAsyncContextManager[Self]] | None = (
            None
        )

        # Set up logger with the actual class module name (not the base class)
        from wappa.core.logging.logger import get_logger

        self.logger = get_logger(self.__class__.__module__)

        # Default handlers for all webhook types (core framework infrastructure)
        # These are shared across clones (stateless)
        self._default_message_handler = DefaultMessageHandler()
        self._default_status_handler = DefaultStatusHandler()
        self._default_error_handler = DefaultErrorHandler()
        self._default_system_handler = DefaultSystemHandler()
        self._default_conversation_handler = DefaultConversationEventHandler()

        # Hook list for API post-process extensibility (replaces monkey-patching)
        self._api_post_process_hooks: list[Callable] = []

    def with_context(
        self,
        inbox_id: str | None,
        user_id: str | None,
        messenger: IMessenger | None,
        cache_factory: ICacheFactory | None,
        db: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
        db_read: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
        inbox_ref: InboxRef | None = None,
        platforms: Mapping[PlatformType, PlatformEntry] | None = None,
    ) -> Self:
        """
        Create a context-bound copy of this handler for a specific request.

        This method implements the Clone Pattern to ensure thread safety.
        Each request gets its own handler instance with isolated context,
        preventing race conditions when concurrent requests are processed.

        Args:
            inbox_id: Inbox identifier for this request, or ``None`` when unscoped
            user_id: User identifier for this request, or ``None`` when unscoped
            messenger: IMessenger instance for this request's inbox
            cache_factory: Cache factory for this request's context
            db: Optional database write session factory
            db_read: Optional database read session factory
            platforms: The app's Platform Registry table that builds the
                Platform Messenger (``PLATFORMS`` when omitted)

        Returns:
            A new handler instance with the specified context bound

        Example:
            # WebhookController creates cloned handler per request:
            request_handler = base_handler.with_context(
                inbox_id="acme_corp",
                user_id="5551234567",
                messenger=messenger,
                cache_factory=cache_factory,
            )
            await request_handler.handle_message(webhook)
        """
        # Shallow copy preserves configuration (default handlers, logger config)
        handler = copy.copy(self)

        # Bind per-request context
        handler.inbox_id = inbox_id
        handler.inbox_ref = inbox_ref
        handler.user_id = user_id

        # Bind per-request dependencies
        handler.messenger = messenger
        handler.cache_factory = cache_factory
        handler.db = db
        handler.db_read = db_read

        # The Platform Messenger extends this same Messenger, so its sends run
        # the same middleware. The registry entry builds it; the handler binds
        # it under the Platform's value (``self.whatsapp``, ``self.instagram``).
        handler.whatsapp = None
        handler.instagram = None
        if messenger is not None:
            from wappa.platforms import platform_messenger

            extended = platform_messenger(messenger, platforms)
            if extended is not None:
                setattr(handler, messenger.platform.value, extended)

        return handler

    def require_database(
        self,
    ) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        """Return the Primary Session Factory or raise one direct error.

        ``db`` stays optional; Wappa never installs a fake session factory.
        Use this when a handler cannot do its work without the database.
        """
        if self.db is None:
            raise RuntimeError(
                "self.db is not available — PostgresDatabasePlugin is not "
                "configured for this application"
            )
        return self.db

    def scope(
        self,
        *,
        inbox_ref: InboxRef | None = None,
        user_id: str | None = None,
    ) -> AbstractAsyncContextManager[Self]:
        """Open prepared context for another User or Inbox found while working.

        Yields a fresh handler built by the same Dispatch Context builder, with
        isolated SSE identity; the current scope is restored on exit.
        ``inbox_ref`` defaults to this handler's Inbox, and ``user_id`` goes
        through the Host identity resolver. Available on handlers Wappa bound
        through that builder: scheduled and Platform webhook dispatch.

        Example:
            async with self.scope(user_id=owner_id) as owner:
                cache = owner.cache_factory.create_user_cache()
                await cache.upsert({"last_digest": event.dispatched_at.isoformat()})
        """
        if self._scope_opener is None:
            raise RuntimeError(
                "self.scope() needs a handler bound by Wappa's Dispatch Context "
                "builder; it is available inside scheduled and webhook dispatch"
            )
        return self._scope_opener(
            inbox_ref=inbox_ref if inbox_ref is not None else self.inbox_ref,
            user_id=user_id,
        )
