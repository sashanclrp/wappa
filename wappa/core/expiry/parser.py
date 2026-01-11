"""
Expiry Event Parser - Parses expired Redis keys and extracts metadata.

Single Responsibility: Parse expiry event messages and extract structured data.
Addresses DRY violation by delegating to registry.resolve().
"""

import logging
from dataclasses import dataclass

from .registry import AsyncHandler, ExpirationHandlerRegistry

logger = logging.getLogger(__name__)


@dataclass
class ExpiryEvent:
    """
    Parsed expiry event data.

    Contains all extracted metadata from an expired Redis key.
    """

    expired_key: str
    handler: AsyncHandler
    identifier: str
    action: str

    @property
    def handler_name(self) -> str:
        """Get handler function name for logging."""
        return self.handler.__name__


@dataclass
class ExpiryEventParser:
    """
    Parses expired Redis keys and resolves handlers.

    Responsibilities:
        - Decode raw message data to string
        - Delegate key parsing to registry.resolve() (DRY principle)
        - Extract action name from key prefix
        - Return structured ExpiryEvent or None

    Design:
        Uses registry.resolve() exclusively to avoid duplicate parsing logic.
        The registry already implements key parsing - we reuse it.

    Usage:
        parser = ExpiryEventParser(registry=expiry_registry)
        event = parser.parse(raw_message)
        if event:
            await dispatcher.dispatch(event)
    """

    registry: ExpirationHandlerRegistry

    def parse(self, message: dict) -> ExpiryEvent | None:
        """
        Parse a Redis PubSub message into an ExpiryEvent.

        Args:
            message: Raw Redis PubSub message dict with 'type' and 'data' keys

        Returns:
            ExpiryEvent if message is valid and handler exists, None otherwise
        """
        if message is None:
            return None

        if message.get("type") != "message":
            return None

        expired_key = self._extract_key(message)
        if not expired_key:
            return None

        # Use registry.resolve() to avoid duplicate parsing logic (DRY)
        resolved = self.registry.resolve(expired_key)
        if not resolved:
            logger.debug("No handler registered for key: %s", expired_key)
            return None

        handler, identifier = resolved
        action = self._extract_action(expired_key)

        logger.debug(
            "Expiry event detected: action=%s, identifier=%s",
            action,
            identifier,
        )

        return ExpiryEvent(
            expired_key=expired_key,
            handler=handler,
            identifier=identifier,
            action=action,
        )

    def _extract_key(self, message: dict) -> str | None:
        """
        Extract and decode the expired key from message.

        Args:
            message: Raw Redis PubSub message

        Returns:
            Decoded key string or None
        """
        expired_key = message.get("data", "")

        if isinstance(expired_key, bytes):
            expired_key = expired_key.decode("utf-8")

        if not expired_key:
            return None

        return expired_key

    def _extract_action(self, key: str) -> str:
        """
        Extract action name from trigger key.

        Pattern: {tenant}:EXPTRIGGER:{action}:{identifier}

        Args:
            key: Full Redis key

        Returns:
            Action name or "unknown"
        """
        parts = key.split(":")
        if len(parts) >= 3:
            return parts[2]
        return "unknown"
