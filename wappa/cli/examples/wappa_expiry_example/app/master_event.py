"""
Master Event Handler - Message Accumulation and Expiry Trigger Management

Handles incoming messages by:
1. Accumulating messages in UserCache with timestamps
2. Creating/resetting 15-second expiry triggers
3. Showing real-time feedback to users

When expiry fires (15s inactivity), the expiry handler echoes all messages back.
"""

from datetime import UTC, datetime

from wappa import WappaEventHandler
from wappa.webhooks import InboundMessageWebhook


class MasterEventHandler(WappaEventHandler):
    """Event handler for message accumulation with expiry tracking."""

    async def process_message(self, webhook: InboundMessageWebhook) -> None:
        """
        Process incoming message by accumulating it and managing expiry trigger.

        Flow:
        1. Get user ID and message details
        2. Load current message list from UserCache (or create new)
        3. Append new message with timestamp
        4. Save back to UserCache
        5. Create/reset 15-second expiry trigger
        6. Send confirmation to user

        Args:
            webhook: Incoming WhatsApp webhook with message data
        """
        try:
            user_id = webhook.user.user_id
            message_text = self._extract_message_content(webhook)

            self.logger.info(
                f"📬 Message from {user_id}: '{message_text[:50]}...' "
                f"(type: {webhook.get_message_type_name()})"
            )

            # 1. Get or create message accumulator from user cache
            user_cache = self.cache_factory.create_user_cache()
            user_data = await user_cache.get() or {}

            messages = user_data.get("messages", [])
            message_count = len(messages)

            # 2. Add new message with timestamp
            new_message = {
                "timestamp": datetime.now(UTC).isoformat(),
                "text": message_text,
                "type": webhook.get_message_type_name(),
            }
            messages.append(new_message)

            # 3. Save back to user cache
            user_data["messages"] = messages
            user_data["last_message_at"] = new_message["timestamp"]
            await user_cache.upsert(user_data, ttl=300)  # 5 min TTL for safety

            self.logger.info(
                f"💾 Stored message #{len(messages)} for user {user_id} in UserCache"
            )

            # 4. Create/reset 15-second expiry trigger
            expiry_cache = self.cache_factory.create_expiry_cache()

            # Delete old trigger if exists (to reset timer)
            await expiry_cache.delete("user_inactivity", user_id)

            # Create new 15-second trigger
            success = await expiry_cache.set(
                action="user_inactivity",
                identifier=user_id,
                ttl_seconds=15,
            )

            if success:
                self.logger.info(
                    f"⏰ Started/reset 15s inactivity timer for user {user_id}"
                )
            else:
                self.logger.error(
                    f"❌ Failed to create expiry trigger for user {user_id}"
                )

            # 5. Send real-time feedback
            await self._send_feedback(user_id, len(messages), message_count == 0)

        except Exception as e:
            self.logger.error(f"❌ Error handling message: {e}", exc_info=True)
            await self.messenger.send_text(
                recipient=webhook.user.user_id,
                text="⚠️ Sorry, something went wrong processing your message.",
            )

    def _extract_message_content(self, webhook: InboundMessageWebhook) -> str:
        """
        Extract message content as text for storage.

        Handles different message types:
        - text: Direct text content
        - image/video/audio/document: Media type description
        - interactive: Button/list selection
        - location: Location coordinates
        - contacts: Contact info
        - sticker: Sticker emoji

        Args:
            webhook: Incoming message webhook

        Returns:
            String representation of message content
        """
        message_type = webhook.get_message_type_name()

        if message_type == "text":
            return webhook.get_message_text() or ""

        elif message_type == "image":
            caption = webhook.get_media_caption()
            return f"📷 [Image{f': {caption}' if caption else ''}]"

        elif message_type == "video":
            caption = webhook.get_media_caption()
            return f"🎥 [Video{f': {caption}' if caption else ''}]"

        elif message_type == "audio":
            return "🎵 [Audio message]"

        elif message_type == "voice":
            return "🎤 [Voice message]"

        elif message_type == "document":
            filename = webhook.get_media_filename()
            return f"📄 [Document: {filename or 'file'}]"

        elif message_type == "sticker":
            return "😀 [Sticker]"

        elif message_type == "location":
            return "📍 [Location shared]"

        elif message_type == "contacts":
            return "👤 [Contact shared]"

        elif message_type == "interactive":
            selection = webhook.get_interactive_selection()
            return f"🔘 [Selected: {selection}]"

        else:
            return f"[{message_type} message]"

    async def _send_feedback(
        self, user_id: str, message_count: int, is_first: bool
    ) -> None:
        """
        Send real-time feedback to user about message accumulation.

        Args:
            user_id: User phone number
            message_count: Total messages accumulated
            is_first: Whether this is the first message
        """
        if is_first:
            feedback = (
                "👋 *Welcome to Wappa Expiry Example!*\n\n"
                "📨 Your message has been received and stored.\n\n"
                "⏰ *How it works:*\n"
                "• I'm accumulating your messages\n"
                "• After 15 seconds of inactivity, I'll echo them all back\n"
                "• Each new message resets the timer\n\n"
                "💡 *Try it:* Send multiple messages quickly, then wait 15 seconds!"
            )
        else:
            feedback = (
                f"✅ Message #{message_count} stored!\n\n"
                f"⏰ Timer reset to 15 seconds\n\n"
                f"💬 Total messages: {message_count}\n"
                f"⏳ I'll echo everything back after 15s of inactivity"
            )

        await self.messenger.send_text(recipient=user_id, text=feedback)
