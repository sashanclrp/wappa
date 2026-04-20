# Re-export shim: canonical types live in wappa.schemas.core.types.
# This module exists only to preserve existing imports under wappa.webhooks.*
# without forcing a full migration. New code should import from schemas.core.types.
from wappa.schemas.core.types import (  # noqa: F401
    PLATFORM_CAPABILITIES,
    ConversationType,
    ErrorCode,
    InteractiveType,
    MediaType,
    MessageMetadata,
    MessageStatus,
    MessageType,
    PlatformData,
    PlatformType,
    ProcessingPriority,
    UniversalMessageData,
    UserRole,
    WebhookType,
    get_max_media_size,
    get_max_text_length,
    get_platform_capabilities,
    is_interactive_type_supported,
    is_message_type_supported,
)
