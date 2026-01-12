"""
Cache Utilities for DB + Redis Echo Example.

Helper class for Redis cache operations:
- Conversation management (get or create)
- Chat record lookups

This module follows the Single Responsibility Principle -
it handles ONLY cache operations with Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import select

from wappa.webhooks import IncomingMessageWebhook

from ..models.cache_models import ConversationCache
from ..models.database_models import Chat, Platform

# Cache TTL constant for conversation data (24 hours)
CONVERSATION_CACHE_TTL = 86400


class CacheHelper:
    """
    Helper class for common cache operations.

    Follows Interface Segregation Principle - only depends on cache_factory.
    """

    def __init__(self, cache_factory, db_session_factory=None):
        """
        Initialize CacheHelper with cache factory.

        Args:
            cache_factory: Wappa cache factory instance (ICacheFactory)
            db_session_factory: Optional database session factory for chat lookups
        """
        self.cache_factory = cache_factory
        self.db = db_session_factory

    async def get_or_create_conversation(
        self,
        user_cache,
        user_id: str,
        webhook: IncomingMessageWebhook,
    ) -> ConversationCache:
        """
        Get or create conversation in Redis cache.

        Args:
            user_cache: User cache instance from cache_factory
            user_id: User identifier
            webhook: Incoming message webhook

        Returns:
            ConversationCache instance
        """
        # Try to get existing conversation
        conversation = await user_cache.get(models=ConversationCache)

        if conversation:
            return conversation

        # Get or create chat in DB (requires db_session_factory)
        chat_id = await self._get_or_create_chat(user_id, webhook)

        # Create new conversation in cache
        now = datetime.now(UTC).isoformat()
        conversation = ConversationCache(
            conversation_id=str(uuid4()),
            chat_id=chat_id,
            started_at=now,
            last_activity_at=now,
        )

        await user_cache.upsert(conversation.model_dump(), ttl=CONVERSATION_CACHE_TTL)

        return conversation

    async def _get_or_create_chat(
        self, user_id: str, webhook: IncomingMessageWebhook
    ) -> str:
        """
        Get or create chat record in database.

        Args:
            user_id: User identifier
            webhook: Incoming message webhook

        Returns:
            Chat ID as string
        """
        if not self.db:
            # If no database session factory, generate a temporary chat_id
            return str(uuid4())

        async with self.db() as session:
            # Try to find existing chat
            statement = select(Chat).where(
                Chat.platform == Platform.WHATSAPP,
                Chat.platform_user_id == user_id,
            )
            result = await session.execute(statement)
            chat = result.scalars().first()

            if chat:
                return str(chat.chat_id)

            # Create new chat
            chat = Chat(
                platform=Platform.WHATSAPP,
                platform_user_id=user_id,
                phone_e164=webhook.user.phone_number or user_id,
                first_name=webhook.user.profile_name or None,
                last_inbound_at=datetime.now(UTC),
            )
            session.add(chat)
            await session.commit()
            await session.refresh(chat)

            return str(chat.chat_id)

    async def get_conversation(self) -> ConversationCache | None:
        """
        Get current conversation from cache.

        Returns:
            ConversationCache or None if not found
        """
        user_cache = self.cache_factory.create_user_cache()
        return await user_cache.get(models=ConversationCache)

    async def save_conversation(
        self, conversation: ConversationCache, ttl: int = CONVERSATION_CACHE_TTL
    ) -> bool:
        """
        Save conversation to cache.

        Args:
            conversation: ConversationCache to save
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            user_cache = self.cache_factory.create_user_cache()
            await user_cache.upsert(conversation.model_dump(), ttl=ttl)
            return True
        except Exception:
            return False

    async def delete_conversation(self) -> bool:
        """
        Delete conversation from cache.

        Returns:
            True if successful, False otherwise
        """
        try:
            user_cache = self.cache_factory.create_user_cache()
            await user_cache.delete()
            return True
        except Exception:
            return False


__all__ = [
    "CONVERSATION_CACHE_TTL",
    "CacheHelper",
]
