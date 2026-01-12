"""
Message Handlers for DB + Redis Echo Example.

Handles different message types and builds echo responses:
- Text messages
- Image, video, audio, document (media) messages
- Contact messages
- Location messages
- Interactive messages
- Sticker messages

This module follows the Single Responsibility Principle -
it handles ONLY message processing and echo response building.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from wappa.webhooks import IncomingMessageWebhook

from ..models.cache_models import CachedMessage
from ..utils.cache_utils import CacheHelper
from ..utils.extraction_utils import (
    determine_message_kind,
    extract_contact_data,
    extract_json_content,
    extract_media_data,
)

# Cache TTL constant for conversation data (24 hours)
CONVERSATION_CACHE_TTL = 86400


class MessageHandlers:
    """
    Handlers for different message types with echo functionality.

    Follows Interface Segregation Principle - only depends on required dependencies.
    """

    def __init__(self, messenger, cache_factory, logger):
        """
        Initialize message handlers.

        Args:
            messenger: IMessenger instance for sending messages
            cache_factory: Cache factory for Redis operations
            logger: Logger instance
        """
        self.messenger = messenger
        self.cache_factory = cache_factory
        self.cache_helper = CacheHelper(cache_factory)
        self.logger = logger

    async def handle_message(self, webhook: IncomingMessageWebhook) -> dict:
        """
        Handle regular message: cache in Redis and echo back.

        Args:
            webhook: Incoming message webhook

        Returns:
            Result dictionary with operation status
        """
        user_id = webhook.user.user_id
        message_text = webhook.get_message_text() or ""
        message_type = webhook.get_message_type_name()

        try:
            user_cache = self.cache_factory.create_user_cache()

            # Get or create conversation cache
            conversation = await self.cache_helper.get_or_create_conversation(
                user_cache, user_id, webhook
            )

            # Extract data based on message type
            media_data = extract_media_data(webhook)
            json_content_data = extract_json_content(webhook)

            # Cache incoming message
            incoming_msg = CachedMessage(
                message_id=str(uuid4()),
                actor="user",
                kind=determine_message_kind(webhook),
                text_content=message_text,
                platform_message_id=webhook.message.message_id,
                platform_timestamp=datetime.now(UTC).isoformat(),
                # Media fields
                media_mime=media_data["media_mime"],
                media_sha256=media_data["media_sha256"],
                media_url=media_data["media_url"],
                media_caption=media_data["media_caption"],
                media_description=media_data["media_description"],
                media_transcript=media_data["media_transcript"],
                # Structured JSON content
                json_content=json_content_data,
            )
            conversation.add_message(incoming_msg)

            # Get message count for response
            msg_count = conversation.get_message_count()

            # Build echo response based on message type
            response = self._build_echo_response(
                webhook=webhook,
                message_text=message_text,
                media_data=media_data,
                message_count=msg_count,
            )

            await self.messenger.send_text(response, user_id)

            # Cache outgoing message
            outgoing_msg = CachedMessage(
                message_id=str(uuid4()),
                actor="agent",
                kind="text",
                text_content=response,
                created_at=datetime.now(UTC).isoformat(),
            )
            conversation.add_message(outgoing_msg)

            # Save updated conversation to cache
            await user_cache.upsert(
                conversation.model_dump(), ttl=CONVERSATION_CACHE_TTL
            )

            self.logger.info(
                f"Processed {message_type} message from {user_id}, "
                f"conversation now has {msg_count + 1} messages"
            )

            return {
                "success": True,
                "message_type": message_type,
                "message_count": msg_count + 1,
            }

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _build_echo_response(
        self,
        webhook: IncomingMessageWebhook,
        message_text: str,
        media_data: dict,
        message_count: int,
    ) -> str:
        """
        Build appropriate echo response based on message type.

        Args:
            webhook: Incoming message webhook
            message_text: Extracted text content
            media_data: Extracted media metadata
            message_count: Current message count

        Returns:
            Formatted echo response string
        """
        message_type = webhook.get_message_type_name()
        message = webhook.message

        # Text messages
        if message_type == "text":
            return self._build_text_response(message_text, message_count)

        # Image messages
        if message_type == "image":
            return self._build_image_response(media_data, message_count)

        # Video messages
        if message_type == "video":
            return self._build_video_response(media_data, message_count)

        # Audio messages
        if message_type == "audio":
            return self._build_audio_response(message, media_data, message_count)

        # Document messages
        if message_type == "document":
            return self._build_document_response(media_data, message_count)

        # Contact messages
        if message_type == "contact":
            contact_data = extract_contact_data(webhook)
            return self._build_contact_response(contact_data, message_count)

        # Location messages
        if message_type == "location":
            return self._build_location_response(message, message_count)

        # Interactive messages
        if message_type == "interactive":
            selected_value = webhook.get_interactive_selection() or "unknown"
            return self._build_interactive_response(selected_value, message_count)

        # Sticker messages
        if message_type == "sticker":
            return self._build_sticker_response(message, message_count)

        # Unknown/unsupported message types
        return self._build_unknown_response(message_type, message_count)

    def _build_text_response(self, message_text: str, message_count: int) -> str:
        """Build response for text messages."""
        return (
            f"Echo: {message_text}\n\n"
            f"Message #{message_count} in this conversation\n"
            f"Send '/HISTORY' to see count\n"
            f"Send '/CLOSE' to close and persist to DB"
        )

    def _build_image_response(self, media_data: dict, message_count: int) -> str:
        """Build response for image messages."""
        caption = media_data.get("media_caption") or ""
        response = "Image received!\n"
        if caption:
            response += f"Caption: {caption}\n"
        response += f"\nType: {media_data.get('media_mime', 'unknown')}\n"
        response += f"SHA256: {media_data.get('media_sha256', 'N/A')[:16]}...\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_video_response(self, media_data: dict, message_count: int) -> str:
        """Build response for video messages."""
        caption = media_data.get("media_caption") or ""
        response = "Video received!\n"
        if caption:
            response += f"Caption: {caption}\n"
        response += f"\nType: {media_data.get('media_mime', 'unknown')}\n"
        response += f"SHA256: {media_data.get('media_sha256', 'N/A')[:16]}...\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_audio_response(
        self, message, media_data: dict, message_count: int
    ) -> str:
        """Build response for audio messages."""
        is_voice = (
            hasattr(message, "audio")
            and hasattr(message.audio, "voice")
            and message.audio.voice
        )
        response = "Voice message received!\n" if is_voice else "Audio file received!\n"
        response += f"Type: {media_data.get('media_mime', 'unknown')}\n"
        response += f"SHA256: {media_data.get('media_sha256', 'N/A')[:16]}...\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_document_response(self, media_data: dict, message_count: int) -> str:
        """Build response for document messages."""
        filename = media_data.get("media_description", "unknown")
        caption = media_data.get("media_caption") or ""
        response = "Document received!\n"
        response += f"Filename: {filename}\n"
        if caption:
            response += f"Caption: {caption}\n"
        response += f"Type: {media_data.get('media_mime', 'unknown')}\n"
        response += f"SHA256: {media_data.get('media_sha256', 'N/A')[:16]}...\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_contact_response(self, contact_data: dict, message_count: int) -> str:
        """Build response for contact messages."""
        contact_name = contact_data.get("name", "Unknown")
        contact_phone = contact_data.get("phone", "N/A")
        response = "Contact shared!\n"
        response += f"Name: {contact_name}\n"
        if contact_phone != "N/A":
            response += f"Phone: {contact_phone}\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_location_response(self, message, message_count: int) -> str:
        """Build response for location messages."""
        response = "Location shared!\n"
        if hasattr(message, "latitude") and hasattr(message, "longitude"):
            response += f"Coordinates: {message.latitude}, {message.longitude}\n"
        if hasattr(message, "location_name") and message.location_name:
            response += f"Name: {message.location_name}\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_interactive_response(
        self, selected_value: str, message_count: int
    ) -> str:
        """Build response for interactive messages."""
        response = f"Interactive selection: {selected_value}\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_sticker_response(self, message, message_count: int) -> str:
        """Build response for sticker messages."""
        is_animated = (
            hasattr(message, "sticker")
            and hasattr(message.sticker, "animated")
            and message.sticker.animated
        )
        sticker_type = "Animated" if is_animated else "Static"
        response = f"{sticker_type} sticker received!\n"
        response += f"\nMessage #{message_count} in this conversation\n"
        response += "Send '/CLOSE' to persist to DB"
        return response

    def _build_unknown_response(self, message_type: str, message_count: int) -> str:
        """Build response for unknown message types."""
        return (
            f"Message received (type: {message_type})\n\n"
            f"Message #{message_count} in this conversation\n"
            "Send '/CLOSE' to persist to DB"
        )


# Convenience function for direct use
async def handle_message_by_type(
    webhook: IncomingMessageWebhook,
    messenger,
    cache_factory,
    logger,
) -> dict:
    """
    Handle message based on its type (convenience function).

    Args:
        webhook: IncomingMessageWebhook to process
        messenger: IMessenger instance
        cache_factory: Cache factory
        logger: Logger instance

    Returns:
        Result dictionary
    """
    handlers = MessageHandlers(messenger, cache_factory, logger)
    return await handlers.handle_message(webhook)


__all__ = [
    "CONVERSATION_CACHE_TTL",
    "MessageHandlers",
    "handle_message_by_type",
]
