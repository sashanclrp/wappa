"""Errors raised while a Platform adapter translates a routed payload."""

from wappa.schemas.core.types import ErrorCode, PlatformType


class ProcessorError(Exception):
    """Base exception for webhook translation errors."""

    def __init__(self, message: str, error_code: ErrorCode, platform: PlatformType):
        self.message = message
        self.error_code = error_code
        self.platform = platform
        super().__init__(message)


class UnsupportedMessageTypeError(ProcessorError):
    """Raised when an adapter encounters an unsupported message type."""

    def __init__(self, message_type: str, platform: PlatformType):
        super().__init__(
            f"Message type '{message_type}' not supported by {platform.value} processor",
            ErrorCode.UNKNOWN_MESSAGE_TYPE,
            platform,
        )
