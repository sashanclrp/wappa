"""
Base event handler class for Wappa applications.

This provides the interface that developers implement to handle WhatsApp webhooks.
"""

import copy
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, AsyncContextManager, Self

from .default_handlers import (
    DefaultErrorHandler,
    DefaultMessageHandler,
    DefaultStatusHandler,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.domain.events.api_message_event import APIMessageEvent
    from wappa.domain.interfaces.cache_factory import ICacheFactory
    from wappa.domain.interfaces.messaging_interface import IMessenger
    from wappa.webhooks import (
        ErrorWebhook,
        IncomingMessageWebhook,
        StatusWebhook,
    )


class WappaEventHandler(ABC):
    """
    Base class for handling WhatsApp events in Wappa applications.

    Developers inherit from this class and implement the handler methods
    to define their application's behavior for different webhook events.

    Dependencies are injected PER-REQUEST via with_context() method:
    - tenant_id: Tenant identifier for this request's context
    - user_id: User identifier for this request's context
    - messenger: IMessenger created with correct tenant_id for each request
    - cache_factory: Cache factory for tenant-specific data persistence
    - db: Database session factory for write operations (PostgresDatabasePlugin)
    - db_read: Database session factory for read operations (uses replicas if configured)

    IMPORTANT: Each request gets a FRESH handler instance via with_context() to ensure
    thread safety. The base handler acts as a prototype that is cloned per-request.

    This ensures proper multi-tenant support where each webhook is processed
    with the correct tenant-specific context and dependencies.

    Database Availability Across Handler Methods:
        All handler methods have access to self.db when PostgresDatabasePlugin is configured:
        - process_message(): Webhook handler - self.db always available
        - process_status(): Webhook handler - self.db always available
        - process_error(): Webhook handler - self.db always available
        - process_api_message(): API event handler - self.db available when FastAPI Request
                                 is passed to the dispatcher (see note below)

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

    def __init__(self):
        """Initialize event handler as a prototype (dependencies injected via with_context)."""
        # Per-request context (set via with_context() - NOT mutable on prototype)
        self.tenant_id: str | None = None
        self.user_id: str | None = None

        # Per-request dependencies (set via with_context() - NOT mutable on prototype)
        self.messenger: IMessenger | None = None
        self.cache_factory: ICacheFactory | None = None

        # Database session factories (set via with_context())
        # Usage: async with self.db() as session: ...
        self.db: Callable[[], AsyncContextManager[AsyncSession]] | None = None
        self.db_read: Callable[[], AsyncContextManager[AsyncSession]] | None = None

        # Set up logger with the actual class module name (not the base class)
        from wappa.core.logging.logger import get_logger

        self.logger = get_logger(self.__class__.__module__)

        # Default handlers for all webhook types (core framework infrastructure)
        # These are shared across clones (stateless)
        self._default_message_handler = DefaultMessageHandler()
        self._default_status_handler = DefaultStatusHandler()
        self._default_error_handler = DefaultErrorHandler()

    def with_context(
        self,
        tenant_id: str,
        user_id: str,
        messenger: "IMessenger",
        cache_factory: "ICacheFactory",
        db: Callable[[], AsyncContextManager["AsyncSession"]] | None = None,
        db_read: Callable[[], AsyncContextManager["AsyncSession"]] | None = None,
    ) -> Self:
        """
        Create a context-bound copy of this handler for a specific request.

        This method implements the Clone Pattern to ensure thread safety.
        Each request gets its own handler instance with isolated context,
        preventing race conditions when concurrent requests are processed.

        Args:
            tenant_id: Tenant identifier for this request
            user_id: User identifier for this request (sender for webhooks, recipient for API)
            messenger: IMessenger instance for this request's tenant
            cache_factory: Cache factory for this request's context
            db: Optional database write session factory
            db_read: Optional database read session factory

        Returns:
            A new handler instance with the specified context bound

        Example:
            # WebhookController creates cloned handler per request:
            request_handler = base_handler.with_context(
                tenant_id="acme_corp",
                user_id="5551234567",
                messenger=messenger,
                cache_factory=cache_factory,
            )
            await request_handler.handle_message(webhook)
        """
        # Shallow copy preserves configuration (default handlers, logger config)
        handler = copy.copy(self)

        # Bind per-request context
        handler.tenant_id = tenant_id
        handler.user_id = user_id

        # Bind per-request dependencies
        handler.messenger = messenger
        handler.cache_factory = cache_factory
        handler.db = db
        handler.db_read = db_read

        return handler

    async def handle_message(self, webhook: "IncomingMessageWebhook") -> None:
        """
        Handle incoming message webhook using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging (non-optional framework infrastructure)
        2. User processing: Custom business logic (implemented in process_message)
        3. Post-processing: Optional cleanup/metrics

        Args:
            webhook: IncomingMessageWebhook containing the message data
        """
        # 1. Pre-processing: Framework logging (always happens)
        await self._default_message_handler.log_incoming_message(webhook)

        # 2. User processing: Custom business logic
        await self.process_message(webhook)

        # 3. Post-processing: Framework cleanup (future extensibility)
        await self._default_message_handler.post_process_message(webhook)

    @abstractmethod
    async def process_message(self, webhook: "IncomingMessageWebhook") -> None:
        """
        Process incoming message webhook with custom business logic.

        This is where users implement their message processing logic.
        The framework handles logging automatically before calling this method.

        Args:
            webhook: IncomingMessageWebhook containing the message data
        """
        pass

    async def handle_status(self, webhook: "StatusWebhook") -> None:
        """
        Handle message status updates using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging (non-optional framework infrastructure)
        2. User processing: Custom status logic (implemented in process_status)
        3. Post-processing: Framework cleanup (future extensibility)

        Args:
            webhook: StatusWebhook containing the status update
        """
        # 1. Pre-processing: Framework logging (always happens)
        await self._default_status_handler.handle_status(webhook)

        # 2. User processing: Custom business logic (optional)
        await self.process_status(webhook)

    async def process_status(self, webhook: "StatusWebhook") -> None:
        """
        Process status webhook with custom business logic.

        Optional method - override if you need custom status processing.
        The framework handles logging automatically before calling this method.

        Args:
            webhook: StatusWebhook containing the status update
        """
        # Default implementation: no additional processing
        pass

    async def handle_error(self, webhook: "ErrorWebhook") -> None:
        """
        Handle platform errors using Template Method pattern.

        This method provides a structured flow:
        1. Pre-processing: Default logging and escalation (non-optional framework infrastructure)
        2. User processing: Custom error handling (implemented in process_error)
        3. Post-processing: Framework cleanup (future extensibility)

        Args:
            webhook: ErrorWebhook containing error information
        """
        # 1. Pre-processing: Framework logging and escalation (always happens)
        await self._default_error_handler.handle_error(webhook)

        # 2. User processing: Custom business logic (optional)
        await self.process_error(webhook)

    async def process_error(self, webhook: "ErrorWebhook") -> None:
        """
        Process error webhook with custom business logic.

        Optional method - override if you need custom error processing.
        The framework handles logging and escalation automatically before calling this method.

        Args:
            webhook: ErrorWebhook containing error information
        """
        # Default implementation: no additional processing
        pass

    # =========== OUTGOING API MESSAGE HANDLING ===========

    async def handle_api_message(self, event: "APIMessageEvent") -> None:
        """
        Handle API-sent message events using Template Method pattern.

        This method provides a structured flow for outgoing messages sent
        via the REST API (not webhooks):
        1. Pre-processing: Framework logging
        2. User processing: Custom business logic (implemented in process_api_message)
        3. Post-processing: Framework cleanup

        DO NOT OVERRIDE - implement process_api_message() instead.

        Args:
            event: APIMessageEvent containing the outgoing message context
        """
        await self._pre_process_api_message(event)
        await self.process_api_message(event)
        await self._post_process_api_message(event)

    async def process_api_message(self, event: "APIMessageEvent") -> None:
        """
        Process API-sent message event with custom business logic.

        Optional method - override to track outgoing messages, update databases,
        or trigger workflows when messages are sent via the REST API.

        This method is NOT called for webhook-received messages - those go through
        process_message(). This is specifically for messages sent via:
        - POST /api/whatsapp/messages/*
        - POST /api/whatsapp/media/*
        - POST /api/whatsapp/templates/*
        - POST /api/whatsapp/interactive/*

        Default: no-op (does nothing unless overridden).

        Database Access:
            self.db is available when PostgresDatabasePlugin is configured AND the
            API route passes the FastAPI Request to the event dispatcher. Without
            Request, self.db will be None - check before using:

            if self.db:
                async with self.db() as session:
                    # Your database operations
                    pass

        Args:
            event: APIMessageEvent with full context (request, response, tenant)

        Example:
            async def process_api_message(self, event: APIMessageEvent) -> None:
                # Check if database is available
                if not self.db:
                    self.logger.debug("Database not available for API event")
                    return

                # Log outgoing message to database
                async with self.db() as session:
                    message = Message(
                        recipient=event.recipient,
                        message_type=event.message_type,
                        message_id=event.message_id,
                        success=event.response_success,
                    )
                    session.add(message)
                    # Auto-commits on context exit

                # Trigger analytics
                if event.response_success:
                    await self.analytics.track_message_sent(event)
        """
        # Default implementation: no additional processing
        pass

    async def _pre_process_api_message(self, event: "APIMessageEvent") -> None:
        """
        Pre-processing hook for API messages.

        Override to customize pre-processing behavior.
        Default: logs the API message event.
        """
        self.logger.debug(
            f"API message sent: {event.message_type} to {event.recipient} "
            f"(success={event.response_success})"
        )

    async def _post_process_api_message(self, event: "APIMessageEvent") -> None:
        """
        Post-processing hook for API messages.

        Override to customize post-processing behavior.
        Default: no additional processing.
        """
        pass

    def configure_default_handlers(
        self,
        message_handler: DefaultMessageHandler = None,
        status_handler: DefaultStatusHandler = None,
        error_handler: DefaultErrorHandler = None,
    ):
        """
        Configure the default handlers used for message, status and error webhooks.

        This allows users to customize the default behavior without overriding methods.

        Args:
            message_handler: Custom DefaultMessageHandler instance
            status_handler: Custom DefaultStatusHandler instance
            error_handler: Custom DefaultErrorHandler instance
        """
        if message_handler:
            self._default_message_handler = message_handler
        if status_handler:
            self._default_status_handler = status_handler
        if error_handler:
            self._default_error_handler = error_handler

    def get_message_stats(self):
        """Get message processing statistics from default handler."""
        return self._default_message_handler.get_stats()

    def get_status_stats(self):
        """Get status processing statistics from default handler."""
        return self._default_status_handler.get_stats()

    def get_error_stats(self):
        """Get error processing statistics from default handler."""
        return self._default_error_handler.get_stats()

    def get_all_stats(self):
        """Get all webhook processing statistics."""
        return {
            "messages": self.get_message_stats(),
            "status": self.get_status_stats(),
            "errors": self.get_error_stats(),
        }

    def validate_dependencies(self) -> bool:
        """
        Validate that required context and dependencies have been properly injected.

        Returns:
            True if all required context and dependencies are available, False otherwise
        """
        # Validate context (required for proper multi-tenant operation)
        if self.tenant_id is None or self.user_id is None:
            self.logger.error(
                f"Request context not set - tenant_id={self.tenant_id}, user_id={self.user_id}. "
                "Ensure with_context() was called before processing."
            )
            return False

        if self.messenger is None:
            self.logger.error(
                "Messenger dependency not injected - cannot send messages (check WebhookController)"
            )
            return False

        # Cache factory is optional for now (placeholder)
        if self.cache_factory is None:
            self.logger.debug(
                "Cache factory not injected - using placeholder (expected)"
            )
        else:
            self.logger.debug(
                f"Cache factory injected: {type(self.cache_factory).__name__}"
            )

        # Database is optional - only available if PostgresDatabasePlugin is registered
        if self.db is None:
            self.logger.debug(
                "Database not injected - PostgresDatabasePlugin may not be registered"
            )
        else:
            self.logger.debug("Database session factory injected")

        self.logger.debug(
            f"Per-request context validation passed - "
            f"tenant: {self.tenant_id}, user: {self.user_id}, "
            f"messenger: {self.messenger.__class__.__name__} "
            f"(platform: {self.messenger.platform.value})"
        )
        return True

    def get_dependency_status(self) -> dict[str, dict[str, Any]]:
        """
        Get the status of injected context and dependencies for debugging.

        Returns:
            Dictionary containing context and dependency injection status
        """
        return {
            "context": {
                "tenant_id": self.tenant_id,
                "user_id": self.user_id,
                "bound": self.tenant_id is not None and self.user_id is not None,
            },
            "messenger": {
                "injected": self.messenger is not None,
                "type": type(self.messenger).__name__ if self.messenger else None,
                "platform": self.messenger.platform.value if self.messenger else None,
                "tenant_id": self.messenger.tenant_id if self.messenger else None,
            },
            "cache_factory": {
                "injected": self.cache_factory is not None,
                "type": type(self.cache_factory).__name__
                if self.cache_factory
                else None,
                "status": "placeholder" if self.cache_factory is None else "active",
            },
            "db": {
                "injected": self.db is not None,
                "status": "active" if self.db is not None else "not_configured",
            },
            "db_read": {
                "injected": self.db_read is not None,
                "status": "active" if self.db_read is not None else "not_configured",
            },
        }
