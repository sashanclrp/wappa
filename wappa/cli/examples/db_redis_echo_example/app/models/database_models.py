"""
Database Models for Conversation History

SQLModel models following Supabase schema with proper enum handling.
Follows 30x-community enum pattern with custom column types.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

# =============================================================================
# SQL Utilities for Enum Handling
# =============================================================================


def enum_values(enum_cls: type[Enum]) -> list:
    """
    Extract enum values for SQLAlchemy enum configuration.

    This is a top-level function (not lambda) so it can be pickled.

    Args:
        enum_cls: The enum class to extract values from

    Returns:
        List of enum values (not keys)

    Example:
        >>> class Status(str, Enum):
        ...     ACTIVE = "active"
        >>> enum_values(Status)
        ['active']
    """
    return [member.value for member in enum_cls]


def get_enum_column(
    enum_cls: type[Enum],
    column_name: str,
    nullable: bool = False,
    create_type: bool = False,
    native_enum: bool = True,
):
    """
    Create a SQLAlchemy Column for enum fields with proper configuration.

    Args:
        enum_cls: The enum class
        column_name: Name for the database enum type (e.g., "platform_t")
        nullable: Whether the column allows NULL values
        create_type: Whether to create the enum type in the database
        native_enum: Whether to use native database enum support

    Returns:
        SQLAlchemy Column configured for the enum

    Example:
        status: Status = Field(
            sa_column=get_enum_column(Status, "status_t", nullable=False)
        )
    """
    return Column(
        SAEnum(
            enum_cls,
            name=column_name,
            values_callable=enum_values,  # Top-level function - pickleable
            native_enum=native_enum,
            create_type=create_type,
        ),
        nullable=nullable,
    )


# =============================================================================
# Enums (matching Supabase types)
# =============================================================================


class Platform(str, Enum):
    """Platform where the user is writing from (platform_t in Supabase)."""

    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"


class MessageActor(str, Enum):
    """Who produced the message (message_actor_t in Supabase)."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"


class MessageKind(str, Enum):
    """Content type of the message (message_kind_t in Supabase)."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STICKER = "sticker"
    REACTION = "reaction"
    LOCATION = "location"
    CONTACT = "contact"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    UNKNOWN = "unknown"


class ConversationStatus(str, Enum):
    """Status of a conversation (conversation_status_t in Supabase)."""

    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


# =============================================================================
# Chat Model
# =============================================================================


class Chat(SQLModel, table=True):
    """
    Chat represents a user on a specific platform.

    Maps to public.chats table in Supabase.
    """

    __tablename__ = "chats"

    chat_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
    )

    # Platform identification
    platform: Platform = Field(
        sa_column=get_enum_column(
            Platform,
            column_name="platform_t",
            nullable=False,
        )
    )
    platform_user_id: str = Field(
        sa_column=Column(Text, nullable=False),
        description="User ID from the platform (phone, telegram ID, etc.)",
    )

    # Optional user information (nullable for platforms like Telegram)
    phone_e164: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    username: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    first_name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    last_name: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    # Operational fields
    is_blocked: bool = Field(
        default=False,
        sa_column=Column(Boolean, server_default=text("false"), nullable=False),
    )
    last_inbound_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_outbound_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Cached context summaries
    last_conversation_summary: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    # Platform-specific metadata
    profile: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, server_default=text("'{}'::jsonb"), nullable=False),
    )

    # Timestamps
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )


# =============================================================================
# Conversation Model
# =============================================================================


class Conversation(SQLModel, table=True):
    """
    Conversation represents a session of messages with a user.

    Maps to public.conversations table in Supabase.
    Only one open conversation per chat at a time.
    """

    __tablename__ = "conversations"

    conversation_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
    )

    chat_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            nullable=False,
            # Foreign key handled by Supabase
        )
    )

    status: ConversationStatus = Field(
        default=ConversationStatus.OPEN,
        sa_column=get_enum_column(
            ConversationStatus,
            column_name="conversation_status_t",
            nullable=False,
        ),
    )

    # Timestamps
    started_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    last_inbound_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_activity_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    closed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Summary
    conversation_summary: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )


# =============================================================================
# Message Model
# =============================================================================


class Message(SQLModel, table=True):
    """
    Message represents a single message in a conversation.

    Maps to public.messages table in Supabase.
    Supports text, media, and tool messages.
    """

    __tablename__ = "messages"

    message_id: UUID = Field(
        default_factory=uuid4,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
    )

    conversation_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            nullable=False,
        )
    )
    chat_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            nullable=False,
        )
    )

    # Message metadata
    actor: MessageActor = Field(
        sa_column=get_enum_column(
            MessageActor,
            column_name="message_actor_t",
            nullable=False,
        )
    )
    kind: MessageKind = Field(
        default=MessageKind.TEXT,
        sa_column=get_enum_column(
            MessageKind,
            column_name="message_kind_t",
            nullable=False,
        ),
    )

    # Platform identification
    platform: Platform = Field(
        sa_column=get_enum_column(
            Platform,
            column_name="platform_t",
            nullable=False,
        )
    )
    platform_message_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    platform_timestamp: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    # Threading
    in_reply_to_message_id: UUID | None = Field(
        default=None,
        sa_column=Column(PGUUID(as_uuid=True), nullable=True),
    )

    # Content
    text_content: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    json_content: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, server_default=text("'{}'::jsonb"), nullable=False),
    )

    # Media fields
    media_mime: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    media_sha256: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    media_url: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    media_caption: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    media_description: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    media_transcript: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    # Delivery tracking
    delivery_status: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    error_code: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )


__all__ = [
    "Chat",
    "Conversation",
    "ConversationStatus",
    "Message",
    "MessageActor",
    "MessageKind",
    "Platform",
    "enum_values",
    "get_enum_column",
]
