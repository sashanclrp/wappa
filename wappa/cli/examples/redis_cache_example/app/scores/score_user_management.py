"""
User Management Score - Single Responsibility: User profile and caching logic.

This module handles all user-related operations including:
- User profile creation and updates
- User data caching with TTL management
- User activity tracking
"""

from wappa.webhooks import IncomingMessageWebhook

from ..models.redis_demo_models import User
from ..utils.cache_utils import get_cache_ttl
from ..utils.message_utils import extract_user_data
from .score_base import ScoreBase


class UserManagementScore(ScoreBase):
    """
    Handles user profile management and caching operations.

    Follows Single Responsibility Principle by focusing only
    on user-related business logic.
    """

    async def can_handle(self, webhook: IncomingMessageWebhook) -> bool:
        """
        This score handles all webhooks since every message needs user management.

        Args:
            webhook: Incoming message webhook

        Returns:
            Always True since user management is needed for all messages
        """
        return True

    async def process(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Process user data extraction and caching.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if user processing was successful
        """
        if not await self.validate_dependencies():
            return False

        try:
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]
            user_name = user_data["user_name"]

            # Get or create user profile
            user = await self._get_or_create_user(user_id, user_name)

            if user:
                # Update user activity
                await self._update_user_activity(user, user_id)

                # Send welcome/acknowledgment message for regular messages
                await self._send_welcome_message(webhook, user, user_id)

                self._record_processing(success=True)

                self.logger.info(
                    f"👤 User profile updated: {user_id} "
                    f"(messages: {user.message_count}, name: {user.user_name})"
                )
                return True
            else:
                self._record_processing(success=False)
                return False

        except Exception as e:
            await self._handle_error(e, "user_management_processing")
            return False

    async def _get_or_create_user(self, user_id: str, user_name: str) -> User:
        """
        Get existing user or create new one.

        Args:
            user_id: User's phone number ID
            user_name: User's display name

        Returns:
            User profile instance
        """
        try:
            # User identity is already bound in cache_factory, so no key needed
            # The IUserCache.get() method takes only an optional models parameter
            user = await self.user_cache.get(models=User)

            if user:
                # User exists, update name if provided and different
                if (
                    user_name
                    and user_name != "Unknown User"
                    and user.user_name != user_name
                ):
                    user.user_name = user_name
                    self.logger.debug(f"Updated user name: {user_id} -> {user_name}")

                self.logger.debug(f"👤 User cache HIT: {user_id}")
                return user
            else:
                # Create new user profile
                user = User(
                    phone_number=user_id,
                    user_name=user_name if user_name != "Unknown User" else None,
                    message_count=0,  # Will be incremented by increment_message_count()
                )

                self.logger.info(
                    f"👤 User cache MISS: Creating new profile for {user_id}"
                )
                return user

        except Exception as e:
            self.logger.error(f"Error getting/creating user {user_id}: {e}")
            raise

    async def _update_user_activity(self, user: User, user_id: str) -> None:
        """
        Update user activity and save to cache.

        Args:
            user: User profile to update
            user_id: User's phone number ID
        """
        try:
            # Update user activity
            user.increment_message_count()

            # Save updated user data with TTL
            # IUserCache.upsert() takes data dict and optional ttl
            ttl = get_cache_ttl("user")
            await self.user_cache.upsert(user.model_dump(), ttl=ttl)

            self.logger.debug(
                f"User activity updated: {user_id} (count: {user.message_count})"
            )

        except Exception as e:
            self.logger.error(f"Error updating user activity {user_id}: {e}")
            raise

    async def get_user_profile(self) -> User | None:
        """
        Get user profile for other score modules.

        User identity is bound in cache_factory, so no explicit user_id needed.

        Returns:
            User profile or None if not found
        """
        try:
            return await self.user_cache.get(models=User)
        except Exception as e:
            self.logger.error(f"Error getting user profile: {e}")
            return None

    async def _send_welcome_message(
        self, webhook: IncomingMessageWebhook, user: User, user_id: str
    ) -> None:
        """
        Send welcome/acknowledgment message based on user's message count.

        Args:
            webhook: Incoming message webhook
            user: User profile data
            user_id: User's phone number ID
        """
        try:
            message_text = webhook.get_message_text() or ""

            # Don't send welcome for commands (let other scores handle them)
            if message_text.strip().startswith("/"):
                return

            # Step 1: Mark message as read with typing indicator
            read_result = await self.messenger.mark_as_read(
                message_id=webhook.message.message_id,
                typing=True,  # Show typing indicator
            )

            if not read_result.success:
                self.logger.warning(
                    f"⚠️ Failed to mark message as read: {read_result.error}"
                )
            else:
                self.logger.debug(
                    f"✅ Message marked as read with typing indicator: {webhook.message.message_id}"
                )

            # Create personalized welcome message based on message count
            if user.message_count == 1:
                # First message - welcome
                welcome_text = (
                    f"👋 Welcome to Wappa Redis Cache Demo, {user.user_name}!\n\n"
                    f"🎯 Available commands:\n"
                    f"• `/WAPPA` - Enter special state\n"
                    f"• `/EXIT` - Leave special state\n"
                    f"• `/HISTORY` - View message history\n"
                    f"• `/STATS` - View cache statistics\n\n"
                    f"💎 Your profile is cached in Redis!"
                )
            else:
                # Regular acknowledgment
                welcome_text = (
                    f"✅ Message received, {user.user_name}!\n"
                    f"📝 Total messages: {user.message_count}\n"
                    f"💾 Profile cached in Redis"
                )

            # Step 2: Send welcome/acknowledgment message
            result = await self.messenger.send_text(
                recipient=user_id,
                text=welcome_text,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(
                    f"✅ Welcome message sent to {user_id} (marked as read + typing)"
                )
            else:
                self.logger.error(f"❌ Failed to send welcome message: {result.error}")

        except Exception as e:
            self.logger.error(f"Error sending welcome message: {e}")
