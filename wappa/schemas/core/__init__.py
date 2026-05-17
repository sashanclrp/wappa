"""Shared schema primitives for Wappa."""

from .recipient import (
    RecipientIdentifier,
    RecipientKind,
    RecipientRequest,
    ResolvedRecipient,
    apply_recipient_to_payload,
    normalize_recipient_identifier,
    resolve_recipient,
)

# Core types
from .types import (
    ConversationType,
    ErrorCode,
    InteractiveType,
    MediaType,
    MessageStatus,
    MessageType,
    PlatformType,
    WebhookType,
)

__all__ = [
    # Core types
    "PlatformType",
    "MessageType",
    "MessageStatus",
    "WebhookType",
    "InteractiveType",
    "MediaType",
    "ConversationType",
    "ErrorCode",
    "RecipientIdentifier",
    "RecipientRequest",
    "RecipientKind",
    "ResolvedRecipient",
    "apply_recipient_to_payload",
    "normalize_recipient_identifier",
    "resolve_recipient",
]
