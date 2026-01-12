"""
Command Handlers for DB + Redis Echo Example.

Handles special commands:
- /CLOSE: Close conversation and persist to database
- /HISTORY: Show message count from Redis cache

This module follows the Single Responsibility Principle -
it handles ONLY command processing logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import select

from wappa.webhooks import IncomingMessageWebhook

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


class CommandHandlers:
    """
    Handlers for special commands (/CLOSE, /HISTORY).

    Follows Interface Segregation Principle - only depends on required dependencies.
    """

    def __init__(self, messenger, cache_factory, db_session_factory, logger):
        """
        Initialize command handlers.

        Args:
            messenger: IMessenger instance for sending messages
            cache_factory: Cache factory for Redis operations
            db_session_factory: Database session factory (callable returning async context manager)
            logger: Logger instance
        """
        self.messenger = messenger
        self.cache_factory = cache_factory
        self.db = db_session_factory
        self.logger = logger

    async def handle_command(
        self, webhook: IncomingMessageWebhook, command: str
    ) -> dict:
        """
        Route command to appropriate handler method.

        Args:
            webhook: Incoming message webhook
            command: Command string (e.g., "/close", "/history")

        Returns:
            Result dictionary with operation status
        """
        command_lower = command.lower()

        if command_lower == "/close":
            return await self.handle_close(webhook)

        if command_lower == "/history":
            return await self.handle_history(webhook)

        self.logger.warning(f"Unsupported command: {command}")
        return {"success": False, "error": f"Unsupported command: {command}"}

    async def handle_close(self, webhook: IncomingMessageWebhook) -> dict:
        """
        Close conversation: persist to DB and clear Redis cache.

        Args:
            webhook: Incoming message webhook

        Returns:
            Result dictionary with operation status
        """
        user_id = webhook.user.user_id

        try:
            user_cache = self.cache_factory.create_user_cache()
            conversation = await user_cache.get(models=ConversationCache)

            if not conversation or conversation.get_message_count() == 0:
                await self.messenger.send_text(
                    "No active conversation to close.", user_id
                )
                return {
                    "success": True,
                    "closed": False,
                    "reason": "no_active_conversation",
                }

            message_count = conversation.get_message_count()
            self.logger.info(
                f"Closing conversation {conversation.conversation_id} with {message_count} messages"
            )

            # Persist to database
            await self._persist_conversation_to_db(conversation)

            # Clear Redis cache
            await user_cache.delete()

            # Confirm to user
            await self.messenger.send_text(
                f"Conversation closed and {message_count} messages persisted to database!",
                user_id,
            )

            return {
                "success": True,
                "closed": True,
                "message_count": message_count,
                "conversation_id": conversation.conversation_id,
            }

        except Exception as e:
            self.logger.error(f"Error closing conversation: {e}", exc_info=True)
            await self.messenger.send_text(
                "Sorry, an error occurred while closing the conversation.", user_id
            )
            return {"success": False, "error": str(e)}

    async def handle_history(self, webhook: IncomingMessageWebhook) -> dict:
        """
        Show message history count from Redis cache.

        Args:
            webhook: Incoming message webhook

        Returns:
            Result dictionary with operation status
        """
        user_id = webhook.user.user_id

        try:
            user_cache = self.cache_factory.create_user_cache()
            conversation = await user_cache.get(models=ConversationCache)
            msg_count = conversation.get_message_count() if conversation else 0

            if msg_count == 0:
                await self.messenger.send_text(
                    "No messages in current conversation.", user_id
                )
            else:
                await self.messenger.send_text(
                    f"Current conversation has {msg_count} messages in cache.\n"
                    f"Send '/CLOSE' to persist to database.",
                    user_id,
                )

            return {
                "success": True,
                "message_count": msg_count,
            }

        except Exception as e:
            self.logger.error(f"Error getting history: {e}", exc_info=True)
            await self.messenger.send_text(
                "Sorry, an error occurred while retrieving history.", user_id
            )
            return {"success": False, "error": str(e)}

    async def _persist_conversation_to_db(
        self, conversation: ConversationCache
    ) -> None:
        """
        Persist conversation and messages to database.

        Args:
            conversation: ConversationCache with messages to persist
        """
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
                last_activity_at=datetime.fromisoformat(conversation.last_activity_at),
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
                chat.last_conversation_summary = db_conversation.conversation_summary
                session.add(chat)

            self.logger.info(
                f"Persisted conversation {conversation.conversation_id} "
                f"with {message_count} messages to DB"
            )


# Convenience functions for direct use


def is_special_command(text: str) -> bool:
    """
    Check if text is a special command.

    Args:
        text: Message text to check

    Returns:
        True if it's a special command, False otherwise
    """
    text_lower = text.strip().lower()
    return text_lower in ["/close", "/history"]


def get_command_from_text(text: str) -> str:
    """
    Extract command from message text.

    Args:
        text: Message text

    Returns:
        Command string or empty string if not a command
    """
    text_clean = text.strip().lower()
    if is_special_command(text_clean):
        return text_clean
    return ""


# Command mapping for easy lookup
COMMAND_HANDLERS = {
    "/close": "handle_close",
    "/history": "handle_history",
}


__all__ = [
    "CommandHandlers",
    "COMMAND_HANDLERS",
    "get_command_from_text",
    "is_special_command",
]
