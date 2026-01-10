"""
Messenger platform enum with dynamic platform validation.

Provides enum-based validation for messenger platforms based on
enabled platforms from application settings and integration with
existing PlatformType enum from core types.
"""

from enum import Enum

from wappa.core.config.settings import settings
from wappa.schemas.core.types import PlatformType


def create_messenger_platform_enum() -> type[Enum]:
    """
    Create dynamic MessengerPlatformEnum based on enabled platforms.

    This creates an enum with only the platforms that are actually
    configured and enabled in the current environment, integrating
    with the existing PlatformType enum.

    Returns:
        Enum class with enabled messenger platforms
    """
    enabled_platforms = settings.enabled_messenger_platforms

    if not enabled_platforms:
        # Fallback enum if no platforms are enabled
        class MessengerPlatformEnum(str, Enum):
            """No messenger platforms are currently enabled."""

            pass

        return MessengerPlatformEnum

    # Create enum members dynamically based on enabled platforms
    enum_members = {
        platform_name.upper(): platform_name for platform_name in enabled_platforms
    }

    # Create the enum class
    MessengerPlatformEnum = Enum("MessengerPlatformEnum", enum_members, type=str)

    # Add custom methods to the enum class
    def get_platform_names():
        """Get list of all enabled platform names."""
        return list(enabled_platforms.keys())

    def is_valid_platform(platform_name: str) -> bool:
        """Check if platform name is valid and enabled."""
        return platform_name in enabled_platforms

    def to_platform_type(platform_name: str) -> PlatformType:
        """Convert platform name to PlatformType enum."""
        try:
            return PlatformType(platform_name.lower())
        except ValueError as e:
            raise ValueError(
                f"Platform '{platform_name}' is not supported by PlatformType enum"
            ) from e

    # Add methods to the enum class
    MessengerPlatformEnum.get_platform_names = staticmethod(get_platform_names)
    MessengerPlatformEnum.is_valid_platform = staticmethod(is_valid_platform)
    MessengerPlatformEnum.to_platform_type = staticmethod(to_platform_type)

    return MessengerPlatformEnum


# Create the enum instance that will be used throughout the application
MessengerPlatformEnum = create_messenger_platform_enum()


def get_available_platforms() -> dict[str, str]:
    """
    Get available messenger platforms with display names.

    Returns:
        Dict mapping platform names to display names
    """
    platforms_config = settings.enabled_messenger_platforms
    return {name: config.display_name for name, config in platforms_config.items()}


def validate_platform_name(platform: str) -> str:
    """
    Validate platform name against enabled platforms.

    Args:
        platform: Platform name to validate

    Returns:
        Validated platform name

    Raises:
        ValueError: If platform is not enabled or configured
    """
    if not MessengerPlatformEnum.is_valid_platform(platform):
        available = MessengerPlatformEnum.get_platform_names()
        raise ValueError(
            f"Platform '{platform}' is not enabled. "
            f"Available platforms: {', '.join(available)}"
        )
    return platform


def get_platform_type(platform_name: str) -> PlatformType:
    """
    Get PlatformType enum value for a platform name.

    Args:
        platform_name: Platform name to convert

    Returns:
        PlatformType enum value

    Raises:
        ValueError: If platform is not valid or supported
    """
    validated_platform = validate_platform_name(platform_name)
    return MessengerPlatformEnum.to_platform_type(validated_platform)
