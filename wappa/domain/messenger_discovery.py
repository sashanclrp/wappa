"""Operation-level discovery without Platform checks in Host Applications."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MediaLimit(BaseModel):
    """Accepted formats for a family; None denotes unrestricted documents."""

    extensions: tuple[str, ...] | None
    upload_extensions: tuple[str, ...] | None
    mime_types: tuple[str, ...] | None = None
    max_bytes: int
    constraints: tuple[str, ...] = ()


class MessageLimits(BaseModel):
    max_text_length: int
    max_preview_url_text_length: int | None = None
    max_recipient_phone_length: int | None = None
    native_text_max_bytes: int | None = None
    splits_text: bool = False


class MessengerDiscovery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operations: frozenset[str] = frozenset()
    media_operations: frozenset[str] = frozenset()
    typing: bool = False
    read_scope: Literal["message", "thread"] | None = None
    target_kinds: frozenset[str] = frozenset({"direct_message"})
    message_limits: MessageLimits = MessageLimits(max_text_length=4096)
    media_limits: dict[str, MediaLimit] = Field(default_factory=dict)
    # Existing WhatsApp HTTP keys remain available on the shared limit route.
    media_http_limits: dict = Field(default_factory=dict)
