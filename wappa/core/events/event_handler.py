"""
Base event handler class for Wappa applications.

This provides the interface that developers implement to handle WhatsApp webhooks.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .default_handlers import (
    DefaultErrorHandler,
    DefaultMessageHandler,
    DefaultStatusHandler,
)

if TYPE_CHECKING:
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
    - cache_factory: Future cache factory for tenant-specific data persistence (currently None)

    This ensures proper multi-tenant support where each webhook is processed
    with the correct tenant-specific messenger instance.
    """

    def __init__(self):
        """Initialize event handler with None dependencies (injected per-request)."""
        self.messenger: IMessenger = None  # Injected per-request by WebhookController
        self.cache_factory = (
            None  # Injected per-request by WebhookController (placeholder)
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
                "❌ Messenger dependency not injected - cannot send messages (check WebhookController)"
            )
            return False

        # Cache factory is optional for now (placeholder)
        if self.cache_factory is None:
            self.logger.debug(
                "ℹ️  Cache factory not injected - using placeholder (expected)"
            )
        else:
            self.logger.debug(
                f"✅ Cache factory injected: {type(self.cache_factory).__name__}"
            )

        self.logger.debug(
            f"✅ Per-request dependencies validation passed - "
            f"messenger: {self.messenger.__class__.__name__} "
            f"(platform: {self.messenger.platform.value}, tenant: {self.messenger.tenant_id})"
        )
        return True

    def get_dependency_status(self) -> dict:
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
        }
