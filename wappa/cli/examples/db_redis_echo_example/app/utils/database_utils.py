"""
Database Utilities for DB + Redis Echo Example.

Helper class for database operations:
- Chat record management
- Conversation persistence

This module follows the Single Responsibility Principle -
it handles ONLY database operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import select

from ..models.cache_models import ConversationCache
from ..models.database_models import (
    Chat,
    Conversation,
    ConversationStatus,
    Message,
    MessageActor,
    MessageKind,
    Platform,
)


class DatabaseHelper:
    """
    Helper class for database operations.

    Follows Interface Segregation Principle - only depends on db_session_factory.
    """

    def __init__(self, db_session_factory, logger=None):
        """
        Initialize DatabaseHelper.

        Args:
            db_session_factory: Database session factory (callable returning async context manager)
            logger: Optional logger instance
        """
        self.db = db_session_factory
        self.logger = logger

    async def get_or_create_chat(
        self,
        user_id: str,
        phone_number: str | None = None,
        profile_name: str | None = None,
    ) -> str:
        """
        Get or create chat record in database.

        Args:
            user_id: User identifier (platform_user_id)
            phone_number: Optional phone number in E.164 format
            profile_name: Optional profile name

        Returns:
            Chat ID as string
        """
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
                phone_e164=phone_number or user_id,
                first_name=profile_name,
                last_inbound_at=datetime.now(UTC),
            )
            session.add(chat)
            await session.commit()
            await session.refresh(chat)

            if self.logger:
                self.logger.info(f"Created new chat {chat.chat_id} for {user_id}")

            return str(chat.chat_id)

    async def persist_conversation(self, conversation: ConversationCache) -> bool:
        """
        Persist conversation and messages to database.

        Args:
            conversation: ConversationCache with messages to persist

        Returns:
            True if successful, False otherwise
        """
        try:
            conversation_uuid = UUID(conversation.conversation_id)
            chat_uuid = UUID(conversation.chat_id)
            message_count = conversation.get_message_count()

            async with self.db() as session:
                # Create conversation record
                db_conversation = Conversation(
                    conversation_id=conversation_uuid,
                    chat_id=chat_uuid,
                    status=ConversationStatus.CLOSED,
                    started_at=datetime.fromisoformat(conversation.started_at),
                    last_activity_at=datetime.fromisoformat(
                        conversation.last_activity_at
                    ),
                    closed_at=datetime.now(UTC),
                    conversation_summary=f"Conversation with {message_count} messages",
                )
                session.add(db_conversation)

                # Create message records
                for cached_msg in conversation.messages:
                    db_message = Message(
                        message_id=UUID(cached_msg.message_id),
                        conversation_id=conversation_uuid,
                        chat_id=chat_uuid,
                        actor=MessageActor(cached_msg.actor),
                        kind=MessageKind(cached_msg.kind),
                        platform=Platform.WHATSAPP,
                        platform_message_id=cached_msg.platform_message_id,
                        platform_timestamp=(
                            datetime.fromisoformat(cached_msg.platform_timestamp)
                            if cached_msg.platform_timestamp
                            else None
                        ),
                        text_content=cached_msg.text_content,
                        # Media fields
                        media_mime=cached_msg.media_mime,
                        media_sha256=cached_msg.media_sha256,
                        media_url=cached_msg.media_url,
                        media_caption=cached_msg.media_caption,
                        media_description=cached_msg.media_description,
                        media_transcript=cached_msg.media_transcript,
                        # JSON content
                        json_content=cached_msg.json_content or {},
                        created_at=(
                            datetime.fromisoformat(cached_msg.created_at)
                            if cached_msg.created_at
                            else datetime.now(UTC)
                        ),
                    )
                    session.add(db_message)

                # Update chat last_outbound_at
                statement = select(Chat).where(Chat.chat_id == chat_uuid)
                result = await session.execute(statement)
                chat = result.scalars().first()
                if chat:
                    chat.last_outbound_at = datetime.now(UTC)
                    chat.last_conversation_summary = (
                        db_conversation.conversation_summary
                    )
                    session.add(chat)

                if self.logger:
                    self.logger.info(
                        f"Persisted conversation {conversation.conversation_id} "
                        f"with {message_count} messages to DB"
                    )

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error persisting conversation: {e}", exc_info=True)
            return False

    async def get_chat_by_user_id(self, user_id: str) -> Chat | None:
        """
        Get chat record by user ID.

        Args:
            user_id: User identifier (platform_user_id)

        Returns:
            Chat record or None if not found
        """
        async with self.db() as session:
            statement = select(Chat).where(
                Chat.platform == Platform.WHATSAPP,
                Chat.platform_user_id == user_id,
            )
            result = await session.execute(statement)
            return result.scalars().first()

    async def update_chat_activity(self, chat_id: str, is_inbound: bool = True) -> bool:
        """
        Update chat activity timestamp.

        Args:
            chat_id: Chat ID
            is_inbound: Whether the activity is inbound (True) or outbound (False)

        Returns:
            True if successful, False otherwise
        """
        try:
            chat_uuid = UUID(chat_id)

            async with self.db() as session:
                statement = select(Chat).where(Chat.chat_id == chat_uuid)
                result = await session.execute(statement)
                chat = result.scalars().first()

                if not chat:
                    return False

                if is_inbound:
                    chat.last_inbound_at = datetime.now(UTC)
                else:
                    chat.last_outbound_at = datetime.now(UTC)

                session.add(chat)

            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Error updating chat activity: {e}", exc_info=True)
            return False


__all__ = [
    "DatabaseHelper",
]
