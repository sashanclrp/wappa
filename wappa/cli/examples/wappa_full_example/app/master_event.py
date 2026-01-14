"""
Master Event Handler for Wappa Full Example Application

This is the main WappaEventHandler implementation that demonstrates comprehensive
WhatsApp Business API functionality including metadata extraction, interactive
commands, state management, and all message type handling.
"""

import time

from wappa import WappaEventHandler
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook

from .handlers.command_handlers import (
    CommandHandlers,
    get_command_from_text,
    is_special_command,
)
from .handlers.message_handlers import MessageHandlers, handle_message_by_type
from .handlers.state_handlers import StateHandlers, handle_user_in_state
from .models.user_models import UserProfile
from .utils.cache_utils import CacheHelper


class WappaFullExampleHandler(WappaEventHandler):
    """
    Comprehensive WappaEventHandler implementation demonstrating all framework features.

    Features:
    - Complete message type handling with metadata extraction
    - Interactive commands (/button, /list, /cta, /location, /template, /api-stats, /docs) with state management
    - Media relay functionality using media_id
    - User tracking and analytics with Redis cache
    - Professional error handling and logging
    - Welcome messages for first-time users
    - State-based interactive workflows with TTL
    """

    def __init__(self):
        """Initialize the comprehensive Wappa example handler."""
        super().__init__()

        # Handler instances (initialized per request)
        self.cache_helper: CacheHelper | None = None
        self.message_handlers: MessageHandlers | None = None
        self.command_handlers: CommandHandlers | None = None
        self.state_handlers: StateHandlers | None = None

        # Statistics
        self._total_messages = 0
        self._successful_processing = 0
        self._failed_processing = 0
        self._first_time_users = 0
        self._commands_processed = 0
        self._interactive_responses = 0

        self.logger.info(
            "🚀 WappaFullExampleHandler initialized - comprehensive demo ready"
        )

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Main message processing method with comprehensive functionality.

        This method orchestrates:
        1. Dependency validation and setup
        2. User profile management and welcome messages
        3. Message reading acknowledgment
        4. Interactive state checking and processing
        5. Special command handling
        6. Regular message processing with metadata extraction
        7. Statistics tracking and logging

        Args:
            webhook: IncomingMessageWebhook containing message data
        """
        start_time = time.time()
        self._total_messages += 1

        try:
            # 1. Setup dependencies and validate
            if not await self._setup_dependencies():
                self._failed_processing += 1
                return

            # 2. Handle user profile and first-time user welcome
            user_profile = await self._handle_user_profile_and_welcome(webhook)
            if not user_profile:
                self.logger.warning(
                    "Failed to handle user profile, continuing without caching"
                )
                user_profile = UserProfile(phone_number=webhook.user.user_id)

            # 3. Mark message as read (as specified in requirements)
            await self._mark_message_as_read(webhook)

            # Extract basic message info for routing
            user_id = webhook.user.user_id
            message_text = webhook.get_message_text().strip()
            message_type = webhook.get_message_type_name()

            self.logger.info(
                f"📨 Processing {message_type} from {user_id}: "
                f"'{message_text[:50]}{'...' if len(message_text) > 50 else ''}'"
            )

            # 4. Check for active interactive states first
            state_result = await handle_user_in_state(
                webhook, user_profile, self.messenger, self.cache_factory, self.logger
            )

            if state_result is not None:
                # User was in an interactive state - handle accordingly
                if state_result["success"]:
                    self._interactive_responses += 1
                    self._successful_processing += 1
                    self.logger.info(
                        f"✅ Interactive state handled: {state_result.get('selection_type', 'unknown')}"
                    )
                else:
                    self.logger.info(
                        f"🔄 Interactive state reminder sent: {state_result.get('error', 'unknown')}"
                    )

                await self._log_processing_stats(start_time)
                return

            # 5. Check for special commands (only for text messages)
            if message_type == "text" and is_special_command(message_text):
                command = get_command_from_text(message_text)
                await self._handle_special_command(webhook, user_profile, command)
                self._commands_processed += 1
                self._successful_processing += 1
                await self._log_processing_stats(start_time)
                return

            # 6. Handle regular message processing with metadata
            result = await handle_message_by_type(
                webhook, user_profile, self.messenger, self.cache_factory, self.logger
            )

            if result["success"]:
                self._successful_processing += 1
                self.logger.info(f"✅ {message_type} message processed successfully")
            else:
                self._failed_processing += 1
                self.logger.error(
                    f"❌ {message_type} message processing failed: {result.get('error')}"
                )

                # Send error response to user
                await self._send_error_response(
                    webhook, result.get("error", "Processing failed")
                )

            await self._log_processing_stats(start_time)

        except Exception as e:
            self._failed_processing += 1
            self.logger.error(
                f"❌ Critical error in message processing: {e}", exc_info=True
            )

            # Send generic error response
            try:
                await self.messenger.send_text(
                    recipient=webhook.user.user_id,
                    text="❌ Sorry, something went wrong processing your message. Please try again.",
                    reply_to_message_id=webhook.message.message_id,
                )
            except Exception as send_error:
                self.logger.error(f"❌ Failed to send error response: {send_error}")

    async def process_status(self, webhook: StatusWebhook) -> None:
        """
        Process status webhooks from WhatsApp Business API.

        Args:
            webhook: StatusWebhook containing delivery status information
        """
        try:
            status_value = webhook.status.value
            recipient = webhook.recipient_id
            message_id = webhook.message_id

            self.logger.info(
                f"📊 Message status: {status_value.upper()} for {recipient} (msg: {message_id[:20]}...)"
            )

            # You can add custom status processing here
            # For example: update delivery statistics, handle failed deliveries, etc.

        except Exception as e:
            self.logger.error(f"❌ Error processing status webhook: {e}", exc_info=True)

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """
        Process error webhooks from WhatsApp Business API.

        Args:
            webhook: ErrorWebhook containing error information
        """
        try:
            error_count = webhook.get_error_count()
            primary_error = webhook.get_primary_error()

            self.logger.error(
                f"🚨 WhatsApp API error: {error_count} errors, "
                f"primary: {primary_error.error_code} - {primary_error.error_title}"
            )

            # Record error in statistics
            self._failed_processing += 1

            # You can add custom error handling logic here
            # For example: alerting systems, retry mechanisms, etc.

        except Exception as e:
            self.logger.error(f"❌ Error processing error webhook: {e}", exc_info=True)

    async def process_api_message(self, event) -> None:
        """
        Process API-sent message events for comprehensive tracking.

        Tracks ALL API messages (text, media, interactive, templates, specialized)
        in Redis for analytics and monitoring.

        Stores:
        1. Individual message history (7-day TTL)
        2. Global statistics with type breakdown (30-day TTL)
        3. Per-user activity logs (30-day TTL)

        Args:
            event: APIMessageEvent containing message details
        """
        try:
            # Log the API event
            status = "✅" if event.response_success else "❌"
            self.logger.info(
                f"📤 API message sent: {status} {event.message_type} to {event.recipient} "
                f"(id={event.message_id})"
            )

            # Ensure cache helper is available
            if not self.cache_factory:
                self.logger.warning(
                    "Cache factory not available, skipping API tracking"
                )
                return

            cache_helper = CacheHelper(self.cache_factory)

            # Import models
            from datetime import UTC, datetime

            from .models.api_tracking_models import (
                APIMessageHistoryEntry,
            )

            recipient = event.recipient
            message_type = event.message_type

            # 1. Record message history
            history_entry = APIMessageHistoryEntry(
                entry_id=f"api_{int(datetime.now(UTC).timestamp())}_{recipient}",
                timestamp=event.timestamp,
                message_type=message_type,
                recipient=recipient,
                message_id=event.message_id,
                success=event.response_success,
                error=event.response_error,
                request_payload=event.request_payload,
                tenant_id=event.tenant_id,
                owner_id=event.owner_id,
            )
            await cache_helper.save_api_message_history(history_entry)
            self.logger.debug(f"📝 Saved API message history: {history_entry.entry_id}")

            # 2. Update global statistics
            stats = await cache_helper.get_api_message_statistics()

            # Get all unique recipients
            all_activities = await cache_helper.get_all_user_api_activities()
            unique_recipients = {activity.user_id for activity in all_activities}
            unique_recipients.add(recipient)

            stats.update_from_event(
                message_type=message_type,
                success=event.response_success,
                recipient=recipient,
                unique_recipients=unique_recipients,
            )
            await cache_helper.save_api_message_statistics(stats)
            self.logger.debug(
                f"📊 Updated API stats: {stats.total_messages_sent} total, "
                f"{stats.success_rate:.1f}% success rate"
            )

            # 3. Update per-user activity
            user_activity = await cache_helper.get_or_create_user_api_activity(
                recipient
            )
            user_activity.add_message_event(
                message_type=message_type,
                message_id=event.message_id,
                success=event.response_success,
            )
            await cache_helper.save_user_api_activity(user_activity)
            self.logger.debug(
                f"👤 Updated user API activity: {recipient} "
                f"({user_activity.messages_received} received)"
            )

        except Exception as e:
            self.logger.error(
                f"❌ Error processing API message event: {e}", exc_info=True
            )

    async def _setup_dependencies(self) -> bool:
        """Setup handler dependencies and validate state."""
        if not self.validate_dependencies():
            self.logger.error("❌ Dependencies not properly injected")
            return False

        if not self.cache_factory:
            self.logger.error(
                "❌ Cache factory not available - Redis caching unavailable"
            )
            return False

        try:
            # Initialize helper instances
            self.cache_helper = CacheHelper(self.cache_factory)
            self.message_handlers = MessageHandlers(
                self.messenger, self.cache_factory, self.logger
            )
            self.command_handlers = CommandHandlers(
                self.messenger, self.cache_factory, self.logger
            )
            self.state_handlers = StateHandlers(
                self.messenger, self.cache_factory, self.logger
            )

            self.logger.debug("✅ Handler dependencies initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to setup dependencies: {e}", exc_info=True)
            return False

    async def _handle_user_profile_and_welcome(
        self, webhook: IncomingMessageWebhook
    ) -> UserProfile | None:
        """Handle user profile caching and send welcome message to first-time users."""
        try:
            user_id = webhook.user.user_id
            user_name = webhook.user.profile_name

            # Get or create user profile
            user_profile = await self.cache_helper.get_or_create_user_profile(
                user_id, user_name, user_name
            )

            # Send welcome message to first-time users
            if (
                user_profile.is_first_time_user
                and not user_profile.has_received_welcome
            ):
                await self._send_welcome_message(webhook, user_profile)
                user_profile.mark_welcome_sent()
                await self.cache_helper.save_user_profile(user_profile)
                self._first_time_users += 1

            return user_profile

        except Exception as e:
            self.logger.error(f"❌ Error handling user profile: {e}", exc_info=True)
            return None

    async def _send_welcome_message(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> None:
        """Send welcome message with instructions to first-time users."""
        user_id = webhook.user.user_id
        display_name = user_profile.get_display_name()

        welcome_text = (
            f"🎉 *Welcome to Wappa Full Example, {display_name}!*\n\n"
            f"This is a comprehensive demonstration of the Wappa framework capabilities.\n\n"
            f"🚀 *What this example does:*\n"
            f"• Echoes all message types with detailed metadata\n"
            f"• Demonstrates interactive features (buttons, lists, CTA, locations, templates)\n"
            f"• Shows state management with TTL\n"
            f"• Tracks user activity and API messages with Redis cache\n"
            f"• Handles media relay using media_id\n\n"
            f"🎯 *Try these special commands:*\n"
            f"• `/button` - Interactive button demo with animal selection\n"
            f"• `/list` - Interactive list demo with media files\n"
            f"• `/cta` - Call-to-action button with external link\n"
            f"• `/location` - Location sharing demonstration\n"
            f"• `/template` - Template state handler instructions\n"
            f"• `/api-stats` - View comprehensive API activity statistics\n"
            f"• `/docs` - API documentation and help\n\n"
            f"📨 *Send any message type to see it echoed with metadata:*\n"
            f"• Text messages → Echo with metadata\n"
            f"• Images/Videos/Audio/Documents → Relayed using media_id\n"
            f"• Locations → Same location echoed back\n"
            f"• Contacts → Contact information echoed back\n\n"
            f"💡 *Pro tip*: This demo showcases production-ready patterns for building WhatsApp Business applications!"
        )

        try:
            result = await self.messenger.send_text(
                recipient=user_id,
                text=welcome_text,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(
                    f"👋 Welcome message sent to {display_name} ({user_id})"
                )
            else:
                self.logger.error(f"❌ Failed to send welcome message: {result.error}")

        except Exception as e:
            self.logger.error(f"❌ Error sending welcome message: {e}")

    async def _mark_message_as_read(self, webhook: IncomingMessageWebhook) -> None:
        """Mark incoming message as read (as specified in requirements)."""
        try:
            result = await self.messenger.mark_as_read(
                message_id=webhook.message.message_id, typing=False
            )

            if result.success:
                self.logger.debug(
                    f"✅ Message marked as read: {webhook.message.message_id[:20]}..."
                )
            else:
                self.logger.warning(f"⚠️ Failed to mark message as read: {result.error}")

        except Exception as e:
            self.logger.warning(f"⚠️ Error marking message as read: {e}")

    async def _handle_special_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile, command: str
    ) -> None:
        """Handle special commands using command handlers."""
        try:
            if command == "/button":
                result = await self.command_handlers.handle_button_command(
                    webhook, user_profile
                )
            elif command == "/list":
                result = await self.command_handlers.handle_list_command(
                    webhook, user_profile
                )
            elif command == "/cta":
                result = await self.command_handlers.handle_cta_command(
                    webhook, user_profile
                )
            elif command == "/location":
                result = await self.command_handlers.handle_location_command(
                    webhook, user_profile
                )
            elif command == "/template":
                result = await self.command_handlers.handle_template_command(
                    webhook, user_profile
                )
            elif command == "/api-stats":
                result = await self.command_handlers.handle_api_stats_command(
                    webhook, user_profile
                )
            elif command == "/docs":
                result = await self.command_handlers.handle_docs_command(
                    webhook, user_profile
                )
            else:
                self.logger.warning(f"Unsupported command: {command}")
                return

            if result["success"]:
                self.logger.info(f"✅ Command {command} processed successfully")
            else:
                self.logger.error(
                    f"❌ Command {command} processing failed: {result.get('error')}"
                )

        except Exception as e:
            self.logger.error(
                f"❌ Error handling command {command}: {e}", exc_info=True
            )

    async def _send_error_response(
        self, webhook: IncomingMessageWebhook, error_details: str
    ) -> None:
        """Send user-friendly error response when processing fails."""
        try:
            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            error_message = (
                "🚨 *Wappa Full Example - Processing Error*\n\n"
                "❌ An error occurred while processing your message.\n"
                "Our comprehensive demo system encountered an issue.\n\n"
                "🔄 *Please try again* or contact support if the problem persists.\n\n"
                "💡 *Tip*: Try using one of our special commands:\n"
                "`/button` • `/list` • `/cta` • `/location` • `/template` • `/api-stats` • `/docs`"
            )

            result = await self.messenger.send_text(
                recipient=user_id, text=error_message, reply_to_message_id=message_id
            )

            if result.success:
                self.logger.info(f"🚨 Error response sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send error response: {result.error}")

        except Exception as e:
            self.logger.error(f"❌ Error sending error response: {e}")

    async def _log_processing_stats(self, start_time: float) -> None:
        """Log processing statistics."""
        processing_time = int((time.time() - start_time) * 1000)
        success_rate = (
            self._successful_processing / max(1, self._total_messages)
        ) * 100

        self.logger.info(
            f"📊 Processing Stats: "
            f"time={processing_time}ms, "
            f"total={self._total_messages}, "
            f"success={self._successful_processing}, "
            f"failed={self._failed_processing}, "
            f"rate={success_rate:.1f}%, "
            f"new_users={self._first_time_users}, "
            f"commands={self._commands_processed}, "
            f"interactions={self._interactive_responses}"
        )

    async def get_handler_statistics(self) -> dict[str, any]:
        """
        Get comprehensive handler statistics.

        Returns:
            Dictionary with processing statistics and handler metrics
        """
        try:
            success_rate = (
                self._successful_processing / max(1, self._total_messages)
            ) * 100

            stats = {
                "handler_info": {
                    "name": "WappaFullExampleHandler",
                    "description": "Comprehensive WhatsApp Business API demo",
                    "features": [
                        "Complete message type handling",
                        "Interactive commands with state management",
                        "Media relay functionality",
                        "User tracking and analytics",
                        "Welcome messages for first-time users",
                    ],
                },
                "processing_stats": {
                    "total_messages": self._total_messages,
                    "successful_processing": self._successful_processing,
                    "failed_processing": self._failed_processing,
                    "success_rate_percent": round(success_rate, 2),
                },
                "feature_usage": {
                    "first_time_users": self._first_time_users,
                    "commands_processed": self._commands_processed,
                    "interactive_responses": self._interactive_responses,
                },
                "supported_commands": [
                    "/button",
                    "/list",
                    "/cta",
                    "/location",
                    "/template",
                    "/api-stats",
                    "/docs",
                ],
                "supported_message_types": [
                    "text",
                    "image",
                    "video",
                    "audio",
                    "voice",
                    "document",
                    "location",
                    "contact",
                    "contacts",
                    "interactive",
                ],
            }

            # Add cache statistics if available
            if self.cache_helper:
                cache_stats = await self.cache_helper.get_cache_statistics()
                stats["cache_stats"] = cache_stats

            return stats

        except Exception as e:
            self.logger.error(f"❌ Error collecting handler statistics: {e}")
            return {"error": f"Statistics collection failed: {str(e)}"}

    def __str__(self) -> str:
        """String representation of the handler."""
        success_rate = (
            self._successful_processing / max(1, self._total_messages)
        ) * 100
        return (
            f"WappaFullExampleHandler("
            f"messages={self._total_messages}, "
            f"success_rate={success_rate:.1f}%, "
            f"new_users={self._first_time_users}, "
            f"commands={self._commands_processed}, "
            f"interactions={self._interactive_responses}"
            f")"
        )
