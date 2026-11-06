"""
Webhook processor factory for platform-agnostic processor creation.

This module creates and caches the platform-specific webhook processor for an
installed Platform.
"""

from typing import Any

from wappa.core.logging.logger import get_logger
from wappa.processors.base_processor import BaseWebhookProcessor, ProcessorError
from wappa.schemas.core.types import ErrorCode, PlatformType


class ProcessorFactory:
    """
    Factory for creating platform-specific webhook processors.

    Implements singleton pattern with processor caching for performance.
    """

    _instance: "ProcessorFactory | None" = None
    _processors: dict[PlatformType, BaseWebhookProcessor] = {}

    def __new__(cls) -> "ProcessorFactory":
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the factory with logger."""
        if not hasattr(self, "_initialized"):
            self.logger = get_logger(__name__)
            self._initialized = True

    def get_processor(
        self, platform: PlatformType, **kwargs: Any
    ) -> BaseWebhookProcessor:
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

        # Use context-aware logger that automatically gets inbox/user context
        logger = get_logger(__name__)
        logger.info(f"Created and cached processor for platform: {platform.value}")
        return processor

    def _create_processor(
        self, platform: PlatformType, **kwargs: Any
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
        if platform == PlatformType.INSTAGRAM:
            from .instagram_processor import InstagramWebhookProcessor

            return InstagramWebhookProcessor(**kwargs)

        if platform == PlatformType.WHATSAPP:
            from .whatsapp_processor import WhatsAppWebhookProcessor

            return WhatsAppWebhookProcessor(**kwargs)

        raise ProcessorError(
            f"Unknown platform: {platform}", ErrorCode.PLATFORM_ERROR, platform
        )

    def get_supported_platforms(self) -> set[PlatformType]:
        """
        Get the set of platforms supported by this factory.

        Returns:
            Set of supported platform types
        """
        return {
            PlatformType.WHATSAPP,
            PlatformType.INSTAGRAM,
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


# Singleton instance for global access
processor_factory = ProcessorFactory()
