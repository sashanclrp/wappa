"""
Webhook processor factory for platform-agnostic processor creation.

This module provides factory classes for creating platform-specific processors,
schemas, and webhook containers based on incoming webhook data.
"""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.processors.base_processor import BaseWebhookProcessor, ProcessorError
from wappa.schemas.core.base_webhook import BaseWebhook
from wappa.schemas.core.types import ErrorCode, PlatformType


class PlatformDetector:
    """
    Platform detection utility for identifying messaging platforms from webhook data.

    Uses various heuristics including URL patterns, headers, payload structure,
    and platform-specific identifiers to determine the source platform.
    """

    @staticmethod
    def detect_from_payload(payload: dict[str, Any]) -> PlatformType | None:
        """
        Detect platform from webhook payload structure.

        Args:
            payload: Raw webhook payload dictionary

        Returns:
            Detected platform type or None if cannot determine
        """
        if not isinstance(payload, dict):
            return None

        # WhatsApp Business API detection
        if payload.get("object") == "whatsapp_business_account" and "entry" in payload:
            return PlatformType.WHATSAPP

        # Telegram Bot API detection
        if "update_id" in payload and (
            "message" in payload or "callback_query" in payload
        ):
            return PlatformType.TELEGRAM

        # Microsoft Teams detection
        if (
            payload.get("type") in ["message", "messageReaction"]
            and "channelData" in payload
            and payload.get("channelData", {}).get("tenant")
        ):
            return PlatformType.TEAMS

        # Instagram Messaging API detection (similar to WhatsApp but different object)
        if payload.get("object") == "instagram" and "entry" in payload:
            return PlatformType.INSTAGRAM

        return None

    @staticmethod
    def detect_from_url(url_path: str) -> PlatformType | None:
        """
        Detect platform from webhook URL path.

        Args:
            url_path: The URL path of the webhook endpoint

        Returns:
            Detected platform type or None if cannot determine
        """
        path_lower = url_path.lower()

        if "/whatsapp" in path_lower:
            return PlatformType.WHATSAPP
        elif "/telegram" in path_lower:
            return PlatformType.TELEGRAM
        elif "/teams" in path_lower:
            return PlatformType.TEAMS
        elif "/instagram" in path_lower:
            return PlatformType.INSTAGRAM

        return None

    @staticmethod
    def detect_from_headers(headers: dict[str, str]) -> PlatformType | None:
        """
        Detect platform from HTTP headers.

        Args:
            headers: Dictionary of HTTP headers

        Returns:
            Detected platform type or None if cannot determine
        """
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

        # WhatsApp/Facebook webhook signature
        if "x-hub-signature-256" in headers_lower:
            return PlatformType.WHATSAPP

        # Telegram webhook
        if "x-telegram-bot-api-secret-token" in headers_lower:
            return PlatformType.TELEGRAM

        # Microsoft Teams
        if (
            "authorization" in headers_lower
            and "bearer" in headers_lower["authorization"]
        ):
            # Could be Teams, but need more specific detection
            return None

        return None

    @classmethod
    def detect_platform(
        cls,
        payload: dict[str, Any],
        url_path: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> PlatformType:
        """
        Comprehensive platform detection using multiple heuristics.

        Args:
            payload: Raw webhook payload dictionary
            url_path: Optional URL path for additional detection
            headers: Optional HTTP headers for additional detection

        Returns:
            Detected platform type

        Raises:
            ProcessorError: If platform cannot be detected
        """
        # Try payload detection first (most reliable)
        platform = cls.detect_from_payload(payload)
        if platform:
            return platform

        # Try URL path detection
        if url_path:
            platform = cls.detect_from_url(url_path)
            if platform:
                return platform

        # Try header detection
        if headers:
            platform = cls.detect_from_headers(headers)
            if platform:
                return platform

        # If all detection methods fail, raise error
        raise ProcessorError(
            "Unable to detect platform from webhook data",
            ErrorCode.PLATFORM_ERROR,
            PlatformType.WHATSAPP,  # Default for error reporting
        )


class ProcessorFactory:
    """
    Factory for creating platform-specific webhook processors.

    Implements singleton pattern with processor caching for performance
    and provides automatic platform detection and processor instantiation.
    """

    _instance: "ProcessorFactory | None" = None
    _processors: dict[PlatformType, BaseWebhookProcessor] = {}

    def __new__(cls) -> "ProcessorFactory":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the factory with logger."""
        if not hasattr(self, "_initialized"):
            self.logger = get_logger(__name__)
            self._initialized = True

    def get_processor(self, platform: PlatformType, **kwargs) -> BaseWebhookProcessor:
        """
        Get or create a processor for the specified platform.

        Args:
            platform: The platform type to get processor for
            **kwargs: Additional processor configuration parameters

        Returns:
            Platform-specific processor instance

        Raises:
            ProcessorError: If processor cannot be created for platform
        """
        # Return cached processor if available
        if platform in self._processors:
            return self._processors[platform]

        # Create new processor based on platform
        processor = self._create_processor(platform, **kwargs)

        # Cache the processor
        self._processors[platform] = processor

        # Use context-aware logger that automatically gets tenant/user context
        logger = get_logger(__name__)
        logger.info(f"Created and cached processor for platform: {platform.value}")
        return processor

    def _create_processor(
        self, platform: PlatformType, **kwargs
    ) -> BaseWebhookProcessor:
        """
        Create a new processor instance for the specified platform.

        Args:
            platform: The platform type to create processor for
            **kwargs: Additional processor configuration parameters

        Returns:
            New processor instance

        Raises:
            ProcessorError: If processor class not found for platform
        """
        if platform == PlatformType.WHATSAPP:
            from .whatsapp_processor import WhatsAppWebhookProcessor

            return WhatsAppWebhookProcessor(**kwargs)

        elif platform == PlatformType.TELEGRAM:
            # TODO: Implement Telegram processor
            # from .telegram_processor import TelegramWebhookProcessor
            # return TelegramWebhookProcessor(**kwargs)
            raise ProcessorError(
                "Telegram processor not yet implemented",
                ErrorCode.PLATFORM_ERROR,
                platform,
            )

        elif platform == PlatformType.TEAMS:
            # TODO: Implement Teams processor
            # from .teams_processor import TeamsWebhookProcessor
            # return TeamsWebhookProcessor(**kwargs)
            raise ProcessorError(
                "Teams processor not yet implemented",
                ErrorCode.PLATFORM_ERROR,
                platform,
            )

        elif platform == PlatformType.INSTAGRAM:
            # TODO: Implement Instagram processor
            # from .instagram_processor import InstagramWebhookProcessor
            # return InstagramWebhookProcessor(**kwargs)
            raise ProcessorError(
                "Instagram processor not yet implemented",
                ErrorCode.PLATFORM_ERROR,
                platform,
            )

        else:
            raise ProcessorError(
                f"Unknown platform: {platform}", ErrorCode.PLATFORM_ERROR, platform
            )

    def get_processor_for_payload(
        self,
        payload: dict[str, Any],
        url_path: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> BaseWebhookProcessor:
        """
        Auto-detect platform and return appropriate processor.

        Args:
            payload: Raw webhook payload dictionary
            url_path: Optional URL path for platform detection
            headers: Optional HTTP headers for platform detection
            **kwargs: Additional processor configuration parameters

        Returns:
            Platform-specific processor instance

        Raises:
            ProcessorError: If platform cannot be detected or processor cannot be created
        """
        try:
            # Detect platform from webhook data
            platform = PlatformDetector.detect_platform(payload, url_path, headers)

            self.logger.info(f"Auto-detected platform: {platform.value}")

            # Get appropriate processor
            return self.get_processor(platform, **kwargs)

        except Exception as e:
            self.logger.error(
                f"Failed to get processor for payload: {e}", exc_info=True
            )
            raise ProcessorError(
                f"Failed to create processor: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,  # Default for error reporting
            ) from e

    def get_supported_platforms(self) -> set[PlatformType]:
        """
        Get the set of platforms supported by this factory.

        Returns:
            Set of supported platform types
        """
        return {
            PlatformType.WHATSAPP,
            # PlatformType.TELEGRAM,    # TODO: Implement
            # PlatformType.TEAMS,       # TODO: Implement
            # PlatformType.INSTAGRAM,   # TODO: Implement
        }

    def is_platform_supported(self, platform: PlatformType) -> bool:
        """
        Check if a platform is supported by this factory.

        Args:
            platform: Platform type to check

        Returns:
            True if platform is supported, False otherwise
        """
        return platform in self.get_supported_platforms()

    def get_processor_capabilities(
        self, platform: PlatformType
    ) -> dict[str, Any] | None:
        """
        Get capabilities for a specific platform processor.

        Args:
            platform: Platform type to get capabilities for

        Returns:
            Capabilities dictionary or None if platform not supported
        """
        if not self.is_platform_supported(platform):
            return None

        try:
            processor = self.get_processor(platform)
            return processor.capabilities.to_dict()
        except Exception as e:
            self.logger.error(f"Failed to get capabilities for {platform.value}: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the processor cache, forcing recreation on next access."""
        self._processors.clear()
        self.logger.info("Processor cache cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get processor cache statistics for monitoring.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_processors": len(self._processors),
            "cached_platforms": [p.value for p in self._processors],
            "supported_platforms": [p.value for p in self.get_supported_platforms()],
            "cache_size_bytes": sum(
                len(str(processor)) for processor in self._processors.values()
            ),
        }


class WebhookFactory:
    """
    Factory for creating platform-specific webhook instances from raw payload data.

    Combines platform detection with schema factory to provide a unified interface
    for parsing webhook payloads from any supported platform.
    """

    def __init__(self):
        """Initialize the webhook factory with schema factory."""
        self.logger = get_logger(__name__)

        # Import schema factory (avoid circular imports)
        from wappa.schemas.factory import schema_factory

        self.schema_factory = schema_factory

    def create_webhook_from_payload(
        self,
        payload: dict[str, Any],
        url_path: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> BaseWebhook:
        """
        Create a webhook instance from raw payload with automatic platform detection.

        Args:
            payload: Raw webhook payload dictionary
            url_path: Optional URL path for platform detection
            headers: Optional HTTP headers for platform detection
            **kwargs: Additional parameters for webhook creation

        Returns:
            Parsed webhook instance with universal interface

        Raises:
            ProcessorError: If platform cannot be detected
            ValidationError: If webhook data is invalid
        """
        try:
            # Detect platform from payload
            platform = PlatformDetector.detect_platform(payload, url_path, headers)

            self.logger.info(
                f"Creating webhook for detected platform: {platform.value}"
            )

            # Create webhook instance using schema factory
            webhook_instance = self.schema_factory.create_webhook_instance(
                platform=platform, webhook_data=payload, **kwargs
            )

            self.logger.debug(
                f"Created webhook instance: {webhook_instance.get_webhook_id()}"
            )

            return webhook_instance

        except Exception as e:
            self.logger.error(
                f"Failed to create webhook from payload: {e}", exc_info=True
            )
            raise ProcessorError(
                f"Failed to create webhook: {e}",
                ErrorCode.PROCESSING_ERROR,
                PlatformType.WHATSAPP,  # Default for error reporting
            ) from e

    def create_webhook_for_platform(
        self, platform: PlatformType, payload: dict[str, Any], **kwargs
    ) -> BaseWebhook:
        """
        Create a webhook instance for a specific platform.

        Args:
            platform: The platform to create webhook for
            payload: Raw webhook payload dictionary
            **kwargs: Additional parameters for webhook creation

        Returns:
            Parsed webhook instance with universal interface

        Raises:
            ValidationError: If webhook data is invalid
        """
        try:
            webhook_instance = self.schema_factory.create_webhook_instance(
                platform=platform, webhook_data=payload, **kwargs
            )

            self.logger.debug(
                f"Created {platform.value} webhook instance: {webhook_instance.get_webhook_id()}"
            )

            return webhook_instance

        except Exception as e:
            self.logger.error(
                f"Failed to create {platform.value} webhook: {e}", exc_info=True
            )
            raise

    def validate_webhook_payload(
        self, payload: dict[str, Any], expected_platform: PlatformType | None = None
    ) -> tuple[bool, str | None, PlatformType | None]:
        """
        Validate webhook payload and return platform information.

        Args:
            payload: Raw webhook payload dictionary
            expected_platform: Optional expected platform for validation

        Returns:
            Tuple of (is_valid, error_message, detected_platform)
        """
        try:
            # Detect platform
            detected_platform = PlatformDetector.detect_platform(payload)

            # Check if detected platform matches expected platform
            if expected_platform and detected_platform != expected_platform:
                return (
                    False,
                    (
                        f"Platform mismatch: expected {expected_platform.value}, "
                        f"detected {detected_platform.value}"
                    ),
                    detected_platform,
                )

            # Try to create webhook instance for validation
            try:
                self.schema_factory.create_webhook_instance(
                    platform=detected_platform, webhook_data=payload
                )
                return True, None, detected_platform

            except Exception as e:
                return False, f"Webhook validation failed: {e}", detected_platform

        except Exception as e:
            return False, f"Platform detection failed: {e}", None

    def get_supported_platforms(self) -> set[PlatformType]:
        """
        Get platforms supported by this factory.

        Returns:
            Set of supported platform types
        """
        return self.schema_factory.webhook_registry.get_supported_platforms()

    def is_platform_supported(self, platform: PlatformType) -> bool:
        """
        Check if a platform is supported by this factory.

        Args:
            platform: Platform type to check

        Returns:
            True if platform is supported, False otherwise
        """
        return self.schema_factory.webhook_registry.is_platform_supported(platform)


# Singleton instances for global access
processor_factory = ProcessorFactory()
webhook_factory = WebhookFactory()
