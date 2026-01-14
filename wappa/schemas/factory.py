"""
Schema factory for platform-agnostic message and webhook schema creation.

This module provides factory classes for dynamically selecting and creating
the appropriate schema classes based on platform and message type combinations.
"""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.schemas.core.base_message import BaseMessage
from wappa.schemas.core.base_webhook import BaseWebhook
from wappa.schemas.core.types import MessageType, PlatformType


class SchemaRegistryError(Exception):
    """Raised when schema registry operations fail."""

    pass


class MessageSchemaRegistry:
    """
    Registry for message schema classes organized by platform and message type.

    Provides centralized registration and lookup of message schema classes
    to enable dynamic schema selection based on incoming webhook data.
    """

    def __init__(self):
        """Initialize the schema registry."""
        self.logger = get_logger(__name__)

        # Registry structure: {platform: {message_type: schema_class}}
        self._message_schemas: dict[
            PlatformType, dict[MessageType, type[BaseMessage]]
        ] = {}

        # Initialize with WhatsApp schemas
        self._register_whatsapp_schemas()

    def _register_whatsapp_schemas(self) -> None:
        """Register all WhatsApp message schema classes."""
        try:
            # Import WhatsApp message schemas
            from .whatsapp.message_types.audio import WhatsAppAudioMessage
            from .whatsapp.message_types.button import WhatsAppButtonMessage
            from .whatsapp.message_types.contact import WhatsAppContactMessage
            from .whatsapp.message_types.document import WhatsAppDocumentMessage
            from .whatsapp.message_types.image import WhatsAppImageMessage
            from .whatsapp.message_types.interactive import WhatsAppInteractiveMessage
            from .whatsapp.message_types.location import WhatsAppLocationMessage
            from .whatsapp.message_types.order import WhatsAppOrderMessage
            from .whatsapp.message_types.reaction import WhatsAppReactionMessage
            from .whatsapp.message_types.sticker import WhatsAppStickerMessage
            from .whatsapp.message_types.system import WhatsAppSystemMessage
            from .whatsapp.message_types.text import WhatsAppTextMessage
            from .whatsapp.message_types.unsupported import WhatsAppUnsupportedMessage
            from .whatsapp.message_types.video import WhatsAppVideoMessage

            # Register WhatsApp schemas
            whatsapp_schemas = {
                MessageType.TEXT: WhatsAppTextMessage,
                MessageType.INTERACTIVE: WhatsAppInteractiveMessage,
                MessageType.IMAGE: WhatsAppImageMessage,
                MessageType.AUDIO: WhatsAppAudioMessage,
                MessageType.VIDEO: WhatsAppVideoMessage,
                MessageType.DOCUMENT: WhatsAppDocumentMessage,
                MessageType.CONTACT: WhatsAppContactMessage,
                MessageType.LOCATION: WhatsAppLocationMessage,
                MessageType.STICKER: WhatsAppStickerMessage,
                MessageType.SYSTEM: WhatsAppSystemMessage,
                MessageType.REACTION: WhatsAppReactionMessage,
                # Additional WhatsApp-specific types (now with proper enum values)
                MessageType.BUTTON: WhatsAppButtonMessage,
                MessageType.ORDER: WhatsAppOrderMessage,
                MessageType.UNSUPPORTED: WhatsAppUnsupportedMessage,
            }

            self._message_schemas[PlatformType.WHATSAPP] = whatsapp_schemas

            self.logger.info(
                f"Registered {len(whatsapp_schemas)} WhatsApp message schemas"
            )

        except ImportError as e:
            self.logger.error(f"Failed to import WhatsApp schemas: {e}")
            raise SchemaRegistryError(
                f"Failed to register WhatsApp schemas: {e}"
            ) from e

    def register_message_schema(
        self,
        platform: PlatformType,
        message_type: MessageType,
        schema_class: type[BaseMessage],
    ) -> None:
        """
        Register a message schema class for a platform and message type.

        Args:
            platform: The platform this schema belongs to
            message_type: The message type this schema handles
            schema_class: The Pydantic model class for this message type

        Raises:
            SchemaRegistryError: If registration fails
        """
        if not issubclass(schema_class, BaseMessage):
            raise SchemaRegistryError(
                f"Schema class must inherit from BaseMessage: {schema_class}"
            )

        if platform not in self._message_schemas:
            self._message_schemas[platform] = {}

        self._message_schemas[platform][message_type] = schema_class

        self.logger.debug(
            f"Registered schema: {platform.value}.{message_type.value} -> {schema_class.__name__}"
        )

    def get_message_schema(
        self, platform: PlatformType, message_type: MessageType
    ) -> type[BaseMessage] | None:
        """
        Get the message schema class for a platform and message type.

        Args:
            platform: The platform to get schema for
            message_type: The message type to get schema for

        Returns:
            Message schema class or None if not found
        """
        platform_schemas = self._message_schemas.get(platform, {})
        return platform_schemas.get(message_type)

    def is_message_type_supported(
        self, platform: PlatformType, message_type: MessageType
    ) -> bool:
        """
        Check if a message type is supported for a platform.

        Args:
            platform: The platform to check
            message_type: The message type to check

        Returns:
            True if supported, False otherwise
        """
        return self.get_message_schema(platform, message_type) is not None

    def get_supported_message_types(self, platform: PlatformType) -> set[MessageType]:
        """
        Get all supported message types for a platform.

        Args:
            platform: The platform to get supported types for

        Returns:
            Set of supported message types
        """
        platform_schemas = self._message_schemas.get(platform, {})
        return set(platform_schemas.keys())

    def get_supported_platforms(self) -> set[PlatformType]:
        """
        Get all platforms with registered schemas.

        Returns:
            Set of platforms with registered schemas
        """
        return set(self._message_schemas.keys())

    def get_registry_stats(self) -> dict[str, Any]:
        """
        Get registry statistics for monitoring.

        Returns:
            Dictionary with registry statistics
        """
        stats = {"total_platforms": len(self._message_schemas), "platforms": {}}

        for platform, schemas in self._message_schemas.items():
            stats["platforms"][platform.value] = {
                "message_types": len(schemas),
                "supported_types": [mt.value for mt in schemas],
            }

        return stats


class WebhookSchemaRegistry:
    """
    Registry for webhook container schema classes organized by platform.

    Provides centralized registration and lookup of webhook container schemas
    for parsing platform-specific webhook structures.
    """

    def __init__(self):
        """Initialize the webhook schema registry."""
        self.logger = get_logger(__name__)

        # Registry structure: {platform: webhook_schema_class}
        self._webhook_schemas: dict[PlatformType, type[BaseWebhook]] = {}

        # Initialize with WhatsApp webhook schema
        self._register_whatsapp_webhook_schema()

    def _register_whatsapp_webhook_schema(self) -> None:
        """Register WhatsApp webhook container schema."""
        try:
            from .whatsapp.webhook_container import WhatsAppWebhook

            self._webhook_schemas[PlatformType.WHATSAPP] = WhatsAppWebhook

            self.logger.info("Registered WhatsApp webhook schema")

        except ImportError as e:
            self.logger.error(f"Failed to import WhatsApp webhook schema: {e}")
            raise SchemaRegistryError(
                f"Failed to register WhatsApp webhook schema: {e}"
            ) from e

    def register_webhook_schema(
        self, platform: PlatformType, schema_class: type[BaseWebhook]
    ) -> None:
        """
        Register a webhook schema class for a platform.

        Args:
            platform: The platform this schema belongs to
            schema_class: The Pydantic model class for webhook containers

        Raises:
            SchemaRegistryError: If registration fails
        """
        if not issubclass(schema_class, BaseWebhook):
            raise SchemaRegistryError(
                f"Schema class must inherit from BaseWebhook: {schema_class}"
            )

        self._webhook_schemas[platform] = schema_class

        self.logger.debug(
            f"Registered webhook schema: {platform.value} -> {schema_class.__name__}"
        )

    def get_webhook_schema(self, platform: PlatformType) -> type[BaseWebhook] | None:
        """
        Get the webhook schema class for a platform.

        Args:
            platform: The platform to get schema for

        Returns:
            Webhook schema class or None if not found
        """
        return self._webhook_schemas.get(platform)

    def is_platform_supported(self, platform: PlatformType) -> bool:
        """
        Check if a platform has a registered webhook schema.

        Args:
            platform: The platform to check

        Returns:
            True if supported, False otherwise
        """
        return platform in self._webhook_schemas

    def get_supported_platforms(self) -> set[PlatformType]:
        """
        Get all platforms with registered webhook schemas.

        Returns:
            Set of supported platforms
        """
        return set(self._webhook_schemas.keys())


class SchemaFactory:
    """
    Factory for creating platform-specific message and webhook schema instances.

    Provides centralized schema selection and instantiation based on platform
    and message type, with comprehensive error handling and validation.
    """

    def __init__(self):
        """Initialize the schema factory with registries."""
        self.logger = get_logger(__name__)

        # Initialize registries
        self.message_registry = MessageSchemaRegistry()
        self.webhook_registry = WebhookSchemaRegistry()

    def create_message_instance(
        self,
        platform: PlatformType,
        message_type: MessageType,
        message_data: dict[str, Any],
        **kwargs,
    ) -> BaseMessage:
        """
        Create a message instance from raw data.

        Args:
            platform: The platform this message came from
            message_type: The type of message to create
            message_data: Raw message data from webhook
            **kwargs: Additional parameters for message creation

        Returns:
            Parsed message instance with universal interface

        Raises:
            SchemaRegistryError: If schema not found for platform/message type
            ValidationError: If message data is invalid
        """
        # Get appropriate schema class
        schema_class = self.message_registry.get_message_schema(platform, message_type)

        if schema_class is None:
            raise SchemaRegistryError(
                f"No schema registered for {platform.value}.{message_type.value}"
            )

        try:
            # Create and validate message instance
            message_instance = schema_class.model_validate(message_data)

            self.logger.debug(
                f"Created {schema_class.__name__} instance: {message_instance.message_id}"
            )

            return message_instance

        except Exception as e:
            self.logger.error(
                f"Failed to create {schema_class.__name__} instance: {e}", exc_info=True
            )
            raise

    def create_webhook_instance(
        self, platform: PlatformType, webhook_data: dict[str, Any], **kwargs
    ) -> BaseWebhook:
        """
        Create a webhook container instance from raw data.

        Args:
            platform: The platform this webhook came from
            webhook_data: Raw webhook payload data
            **kwargs: Additional parameters for webhook creation

        Returns:
            Parsed webhook instance with universal interface

        Raises:
            SchemaRegistryError: If schema not found for platform
            ValidationError: If webhook data is invalid
        """
        # Get appropriate webhook schema class
        schema_class = self.webhook_registry.get_webhook_schema(platform)

        if schema_class is None:
            raise SchemaRegistryError(
                f"No webhook schema registered for {platform.value}"
            )

        try:
            # Create and validate webhook instance
            webhook_instance = schema_class.model_validate(webhook_data)

            self.logger.debug(
                f"Created {schema_class.__name__} instance: {webhook_instance.get_webhook_id()}"
            )

            return webhook_instance

        except Exception as e:
            self.logger.error(
                f"Failed to create {schema_class.__name__} instance: {e}", exc_info=True
            )
            raise

    def detect_message_type(
        self, platform: PlatformType, message_data: dict[str, Any]
    ) -> MessageType | None:
        """
        Detect message type from raw message data.

        Args:
            platform: The platform this message came from
            message_data: Raw message data

        Returns:
            Detected message type or None if cannot determine
        """
        if not isinstance(message_data, dict):
            return None

        # Get type from message data (common pattern across platforms)
        message_type_str = message_data.get("type")
        if not message_type_str:
            return None

        try:
            # Try to convert to MessageType enum
            message_type = MessageType(message_type_str)

            # Verify this message type is supported for the platform
            if self.message_registry.is_message_type_supported(platform, message_type):
                return message_type

        except ValueError:
            # Handle platform-specific message types not in the enum
            if platform == PlatformType.WHATSAPP:
                # WhatsApp-specific message types
                whatsapp_types = {
                    "button": MessageType.INTERACTIVE,  # Map to closest standard type
                    "order": MessageType.INTERACTIVE,  # Map to closest standard type
                    "unsupported": MessageType.SYSTEM,  # Map to closest standard type
                }
                mapped_type = whatsapp_types.get(message_type_str)
                if mapped_type and self.message_registry.is_message_type_supported(
                    platform, mapped_type
                ):
                    return mapped_type

        return None

    def get_supported_combinations(self) -> dict[str, list[str]]:
        """
        Get all supported platform and message type combinations.

        Returns:
            Dictionary mapping platform names to lists of supported message types
        """
        combinations = {}

        for platform in self.message_registry.get_supported_platforms():
            message_types = self.message_registry.get_supported_message_types(platform)
            combinations[platform.value] = [mt.value for mt in message_types]

        return combinations

    def validate_platform_message_compatibility(
        self, platform: PlatformType, message_type: MessageType
    ) -> tuple[bool, str | None]:
        """
        Validate if a platform supports a specific message type.

        Args:
            platform: The platform to check
            message_type: The message type to check

        Returns:
            Tuple of (is_supported, error_message)
        """
        if not self.message_registry.is_message_type_supported(platform, message_type):
            supported_types = self.message_registry.get_supported_message_types(
                platform
            )
            return False, (
                f"Message type '{message_type.value}' not supported for platform '{platform.value}'. "
                f"Supported types: {[mt.value for mt in supported_types]}"
            )

        return True, None

    def get_factory_stats(self) -> dict[str, Any]:
        """
        Get factory statistics for monitoring.

        Returns:
            Dictionary with factory statistics
        """
        return {
            "message_registry": self.message_registry.get_registry_stats(),
            "webhook_registry": {
                "supported_platforms": [
                    p.value for p in self.webhook_registry.get_supported_platforms()
                ]
            },
            "total_combinations": sum(
                len(types) for types in self.get_supported_combinations().values()
            ),
        }

    # ===== Universal Webhook Interface Support =====

    def detect_webhook_type(self, payload: dict[str, Any]) -> str | None:
        """
        Detect webhook type from raw payload structure.

        Based on WhatsApp webhook structure but designed to be universal:
        - IncomingMessage: Contains 'messages' array
        - Status: Contains 'statuses' array
        - Error: Contains 'errors' array at value level
        - OutgoingMessage: Future - currently not supported

        Args:
            payload: Raw webhook payload dictionary

        Returns:
            Webhook type string or None if cannot determine
        """
        if not isinstance(payload, dict):
            return None

        # Navigate to WhatsApp webhook structure: entry[0].changes[0].value
        try:
            entry = payload.get("entry", [])
            if not entry or not isinstance(entry, list):
                return None

            changes = entry[0].get("changes", [])
            if not changes or not isinstance(changes, list):
                return None

            value = changes[0].get("value", {})
            if not isinstance(value, dict):
                return None

            # Check for webhook type indicators
            if (
                "messages" in value
                and isinstance(value["messages"], list)
                and len(value["messages"]) > 0
            ):
                return "incoming_message"
            elif (
                "statuses" in value
                and isinstance(value["statuses"], list)
                and len(value["statuses"]) > 0
            ):
                return "status"
            elif (
                "errors" in value
                and isinstance(value["errors"], list)
                and len(value["errors"]) > 0
            ):
                return "error"

            return None

        except (KeyError, IndexError, TypeError):
            return None

    async def create_universal_webhook(
        self,
        platform: PlatformType,
        payload: dict[str, Any],
        webhook_type: str | None = None,
        **kwargs,
    ) -> "UniversalWebhook":
        """
        Create a Universal Webhook Interface from platform-specific payload.

        This method acts as the main factory for converting platform webhooks
        into universal interfaces. It delegates to platform-specific processors
        to handle the transformation.

        Args:
            platform: The platform this webhook came from
            payload: Raw webhook payload dictionary
            webhook_type: Optional webhook type hint (will auto-detect if None)
            **kwargs: Additional parameters for webhook creation

        Returns:
            Universal webhook interface instance

        Raises:
            SchemaRegistryError: If platform not supported or conversion fails
        """
        from wappa.processors.factory import processor_factory

        try:
            # Get platform-specific processor
            processor = processor_factory.get_processor(platform)

            # Use processor to create universal webhook
            if hasattr(processor, "create_universal_webhook"):
                return await processor.create_universal_webhook(payload, **kwargs)
            else:
                raise SchemaRegistryError(
                    f"Processor for {platform.value} does not support universal webhook creation"
                )

        except Exception as e:
            self.logger.error(
                f"Failed to create universal webhook for {platform.value}: {e}",
                exc_info=True,
            )
            raise SchemaRegistryError(f"Failed to create universal webhook: {e}") from e

    def create_universal_webhook_from_payload(
        self,
        payload: dict[str, Any],
        url_path: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> "UniversalWebhook":
        """
        Create Universal Webhook Interface with automatic platform detection.

        Args:
            payload: Raw webhook payload dictionary
            url_path: Optional URL path for platform detection
            headers: Optional HTTP headers for platform detection
            **kwargs: Additional parameters for webhook creation

        Returns:
            Universal webhook interface instance

        Raises:
            SchemaRegistryError: If platform cannot be detected or conversion fails
        """
        from wappa.processors.factory import PlatformDetector

        try:
            # Detect platform from payload
            platform = PlatformDetector.detect_platform(payload, url_path, headers)

            # Create universal webhook for detected platform
            return self.create_universal_webhook(platform, payload, **kwargs)

        except Exception as e:
            self.logger.error(
                f"Failed to create universal webhook from payload: {e}", exc_info=True
            )
            raise SchemaRegistryError(f"Failed to create universal webhook: {e}") from e

    def validate_universal_webhook_payload(
        self, payload: dict[str, Any], expected_type: str | None = None
    ) -> tuple[bool, str | None, str | None]:
        """
        Validate payload for universal webhook creation.

        Args:
            payload: Raw webhook payload dictionary
            expected_type: Optional expected webhook type for validation

        Returns:
            Tuple of (is_valid, error_message, detected_type)
        """
        try:
            # Detect webhook type
            detected_type = self.detect_webhook_type(payload)

            if not detected_type:
                return (
                    False,
                    "Unable to determine webhook type from payload structure",
                    None,
                )

            # Check if detected type matches expected
            if expected_type and detected_type != expected_type:
                return (
                    False,
                    (
                        f"Webhook type mismatch: expected {expected_type}, "
                        f"detected {detected_type}"
                    ),
                    detected_type,
                )

            # Basic structure validation
            if not self._validate_basic_webhook_structure(payload):
                return (
                    False,
                    "Payload does not match expected webhook structure",
                    detected_type,
                )

            return True, None, detected_type

        except Exception as e:
            return False, f"Validation error: {e}", None

    def _validate_basic_webhook_structure(self, payload: dict[str, Any]) -> bool:
        """
        Validate basic webhook structure (based on WhatsApp format).

        Args:
            payload: Raw webhook payload dictionary

        Returns:
            True if structure is valid, False otherwise
        """
        try:
            # Check for required top-level fields
            if "object" not in payload or "entry" not in payload:
                return False

            # Check entry structure
            entry = payload["entry"]
            if not isinstance(entry, list) or len(entry) == 0:
                return False

            # Check changes structure
            first_entry = entry[0]
            if "changes" not in first_entry:
                return False

            changes = first_entry["changes"]
            if not isinstance(changes, list) or len(changes) == 0:
                return False

            # Check value structure
            first_change = changes[0]
            if "value" not in first_change:
                return False

            value = first_change["value"]
            if not isinstance(value, dict):
                return False

            # Should have metadata at minimum
            return "metadata" in value

        except (KeyError, IndexError, TypeError):
            return False

    def get_supported_webhook_types(self) -> list[str]:
        """
        Get list of supported universal webhook types.

        Returns:
            List of supported webhook type strings
        """
        return ["incoming_message", "status", "error", "outgoing_message"]

    def is_webhook_type_supported(self, webhook_type: str) -> bool:
        """
        Check if a webhook type is supported.

        Args:
            webhook_type: Webhook type string to check

        Returns:
            True if supported, False otherwise
        """
        return webhook_type in self.get_supported_webhook_types()


# Singleton instance for global access
schema_factory = SchemaFactory()
