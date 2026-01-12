"""
Models module for DB + Redis Echo Example.

This module provides data models:
- Cache models: Pydantic models for Redis cache storage
- Database models: SQLModel models for PostgreSQL persistence

All models follow the Single Responsibility Principle.
"""

from .cache_models import CachedMessage, ConversationCache
from .database_models import (
    Chat,
    Conversation,
    ConversationStatus,
    Message,
    MessageActor,
    MessageKind,
    Platform,
)

__all__ = [
    # Cache models
    "CachedMessage",
    "ConversationCache",
    # Database models
    "Chat",
    "Conversation",
    "ConversationStatus",
    "Message",
    "MessageActor",
    "MessageKind",
    "Platform",
]
