"""
Base event handler class for Wappa applications.

This provides the interface that developers implement to handle WhatsApp webhooks.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, AsyncContextManager

from .default_handlers import (
    DefaultErrorHandler,
    DefaultMessageHandler,
    DefaultStatusHandler,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from wappa.domain.events.api_message_event import APIMessageEvent
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

    Dependencies are injected PER-REQUEST by WebhookController:
    - messenger: IMessenger created with correct tenant_id for each request
    - cache_factory: Cache factory for tenant-specific data persistence
    - db: Database session factory for write operations (PostgresDatabasePlugin)
    - db_read: Database session factory for read operations (uses replicas if configured)

    This ensures proper multi-tenant support where each webhook is processed
    with the correct tenant-specific messenger instance.

    Database Usage:
        async with self.db() as session:
            user = await session.exec(select(User).where(User.phone == phone))
            # Auto-commits on context exit if auto_commit=True

        # For read-heavy operations (uses replicas if configured):
        async with self.db_read() as session:
            results = await session.exec(select(User))
    """

    def __init__(self):
        """Initialize event handler with None dependencies (injected per-request)."""
        self.messenger: IMessenger | None = (
            None  # Injected per-request by WebhookController
        )
        self.cache_factory = (
            None  # Injected per-request by WebhookController (placeholder)
        )
        # Database session factories (injected per-request by WebhookController)
        # Usage: async with self.db() as session: ...
        self.db: Callable[[], AsyncContextManager[AsyncSession]] | None = (
            None  # Write session factory (PostgresDatabasePlugin)
        )
        self.db_read: Callable[[], AsyncContextManager[AsyncSession]] | None = (
            None  # Read session factory (uses replicas if configured)
        )

        # Set up logger with the actual class module name (not the base class)
        from wappa.core.logging.logger import get_logger

        self.logger = get_logger(self.__class__.__module__)

        # Default handlers for all webhook types (core framework infrastructure)
        self._default_message_handler = DefaultMessageHandler()
        self._default_status_handler = DefaultStatusHandler()
        self._default_error_handler = DefaultErrorHandler()

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

        Args:
            event: APIMessageEvent with full context (request, response, tenant)

        Example:
            async def process_api_message(self, event: APIMessageEvent) -> None:
                # Log outgoing message to database
                await self.db.insert_message(
                    recipient=event.recipient,
                    message_type=event.message_type,
                    message_id=event.message_id,
                    success=event.response_success,
                )

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
        Validate that required dependencies have been properly injected per-request.

        Returns:
            True if all required dependencies are available, False otherwise
        """
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
            f"Per-request dependencies validation passed - "
            f"messenger: {self.messenger.__class__.__name__} "
            f"(platform: {self.messenger.platform.value}, tenant: {self.messenger.tenant_id})"
        )
        return True

    def get_dependency_status(self) -> dict[str, dict[str, Any]]:
        """
        Get the status of injected dependencies for debugging.

        Returns:
            Dictionary containing dependency injection status
        """
        return {
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
