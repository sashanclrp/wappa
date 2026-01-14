"""
Special command handlers for the Wappa Full Example application.

This module provides handlers for special commands like /button, /list, /cta, and /location
that demonstrate interactive features and specialized messaging capabilities.
"""

import time

from wappa.messaging.whatsapp.models.interactive_models import (
    InteractiveHeader,
    ReplyButton,
)
from wappa.webhooks import IncomingMessageWebhook

from ..models.state_models import ButtonState, ListState, StateType
from ..models.user_models import UserProfile
from ..utils.cache_utils import CacheHelper


class CommandHandlers:
    """Collection of handlers for special commands."""

    def __init__(self, messenger, cache_factory, logger):
        """
        Initialize command handlers.

        Args:
            messenger: IMessenger instance for sending messages
            cache_factory: Cache factory for data persistence
            logger: Logger instance
        """
        self.messenger = messenger
        self.cache_helper = CacheHelper(cache_factory)
        self.logger = logger

    async def handle_button_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /button command - creates interactive button message.

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"🔘 Processing /button command from {user_id}")

            # Clean up any existing button state
            existing_state = await self.cache_helper.get_user_state(
                user_id, StateType.BUTTON
            )
            if existing_state:
                await self.cache_helper.remove_user_state(user_id, StateType.BUTTON)

            # Create button data for state storage (as dictionaries)
            button_data = [
                {"id": "kitty", "title": "🐱 Kitty"},
                {"id": "puppy", "title": "🐶 Puppy"},
            ]

            # Create button objects for WhatsApp messenger
            buttons = [
                ReplyButton(id="kitty", title="🐱 Kitty"),
                ReplyButton(id="puppy", title="🐶 Puppy"),
            ]

            # Create button state with 10 minute TTL (using dictionaries)
            button_state = ButtonState.create_button_state(
                user_id=user_id,
                buttons=button_data,
                message_text="Choose your favorite animal! You have 10 minutes to decide.",
                ttl_seconds=600,  # 10 minutes
                original_message_id=message_id,
            )

            # Save the state
            await self.cache_helper.save_user_state(button_state)

            # Send button message
            button_result = await self.messenger.send_button_message(
                buttons=buttons,
                recipient=user_id,
                body="🎯 *Button Demo Activated!*\n\nChoose your favorite animal below. You have 10 minutes to make your selection, or the state will expire automatically.",
                header=InteractiveHeader(type="text", text="Interactive Button Demo"),
                footer="⏰ Expires in 10 minutes",
                reply_to_message_id=message_id,
            )

            if not button_result.success:
                self.logger.error(
                    f"Failed to send button message: {button_result.error}"
                )
                await self.cache_helper.remove_user_state(user_id, StateType.BUTTON)
                return {"success": False, "error": "Failed to send button message"}

            # Update button state with message ID
            button_state.interactive_message_id = button_result.message_id
            await self.cache_helper.save_user_state(button_state)

            # Send instruction message
            instruction_text = (
                "📋 *How to use this demo:*\n\n"
                "1. ✅ Click one of the buttons above to make your selection\n"
                "2. 📸 You'll receive an image of your chosen animal\n"
                "3. 📊 You'll also receive metadata about your selection\n"
                "4. ⚠️ If you send any other message, I'll remind you to click a button\n"
                "5. ⏰ State expires in 10 minutes if no selection is made\n\n"
                "💡 *Pro tip*: This demonstrates state management with TTL!"
            )

            await self.messenger.send_text(recipient=user_id, text=instruction_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "text", "/button")

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Button command processed in {processing_time}ms")

            return {
                "success": True,
                "command": "/button",
                "state_created": True,
                "state_ttl_seconds": 600,
                "buttons_sent": True,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling /button command: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_list_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /list command - creates interactive list message.

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"📋 Processing /list command from {user_id}")

            # Clean up any existing list state
            existing_state = await self.cache_helper.get_user_state(
                user_id, StateType.LIST
            )
            if existing_state:
                await self.cache_helper.remove_user_state(user_id, StateType.LIST)

            # Create list sections with media options
            sections = [
                {
                    "title": "📁 Media Files",
                    "rows": [
                        {
                            "id": "image_file",
                            "title": "🖼️ Image",
                            "description": "Get a sample image file",
                        },
                        {
                            "id": "video_file",
                            "title": "🎬 Video",
                            "description": "Get a sample video file",
                        },
                        {
                            "id": "audio_file",
                            "title": "🎵 Audio",
                            "description": "Get a sample audio file",
                        },
                        {
                            "id": "document_file",
                            "title": "📄 Document",
                            "description": "Get a sample document file",
                        },
                    ],
                }
            ]

            # Create list state with 10 minute TTL
            list_state = ListState.create_list_state(
                user_id=user_id,
                sections=sections,
                message_text="Choose the type of media file you want to receive!",
                button_text="Choose Media",
                ttl_seconds=600,  # 10 minutes
                original_message_id=message_id,
            )

            # Save the state
            await self.cache_helper.save_user_state(list_state)

            # Send list message
            list_result = await self.messenger.send_list_message(
                sections=sections,
                recipient=user_id,
                body="🎯 *List Demo Activated!*\n\nSelect the type of media file you want to receive. You have 10 minutes to make your selection, or the state will expire automatically.",
                button_text="Choose Media",
                header="Interactive List Demo",
                footer="⏰ Expires in 10 minutes",
                reply_to_message_id=message_id,
            )

            if not list_result.success:
                self.logger.error(f"Failed to send list message: {list_result.error}")
                await self.cache_helper.remove_user_state(user_id, StateType.LIST)
                return {"success": False, "error": "Failed to send list message"}

            # Update list state with message ID
            list_state.interactive_message_id = list_result.message_id
            await self.cache_helper.save_user_state(list_state)

            # Send instruction message
            instruction_text = (
                "📋 *How to use this demo:*\n\n"
                "1. 📱 Tap the 'Choose Media' button above\n"
                "2. 📋 Select one of the 4 media types from the list\n"
                "3. 📎 You'll receive the corresponding media file\n"
                "4. 📊 You'll also receive metadata about your selection\n"
                "5. ⚠️ If you send any other message, I'll remind you to make a selection\n"
                "6. ⏰ State expires in 10 minutes if no selection is made\n\n"
                "💡 *Pro tip*: This demonstrates list interactions with media responses!"
            )

            await self.messenger.send_text(recipient=user_id, text=instruction_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "text", "/list")

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ List command processed in {processing_time}ms")

            return {
                "success": True,
                "command": "/list",
                "state_created": True,
                "state_ttl_seconds": 600,
                "list_sent": True,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling /list command: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_cta_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /cta command - sends call-to-action message.

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"🔗 Processing /cta command from {user_id}")

            # Send CTA message with link to Wappa documentation
            cta_result = await self.messenger.send_cta_message(
                button_text="📚 View Documentation",
                button_url="https://wappa.mimeia.com/docs",
                recipient=user_id,
                body="🎯 *Call-to-Action Demo*\n\nThis is a demonstration of CTA (Call-to-Action) buttons that link to external websites. Click the button below to visit the Wappa framework documentation!",
                header="CTA Button Demo",
                footer="External link - opens in browser",
                reply_to_message_id=message_id,
            )

            if not cta_result.success:
                self.logger.error(f"Failed to send CTA message: {cta_result.error}")
                return {"success": False, "error": "Failed to send CTA message"}

            # Send follow-up explanation
            explanation_text = (
                "📋 *About CTA Buttons:*\n\n"
                "✅ *What just happened:*\n"
                "• A CTA (Call-to-Action) button was sent\n"
                "• It links to: `https://wappa.mimeia.com/docs`\n"
                "• When clicked, it opens in your default browser\n\n"
                "🔗 *Use cases for CTA buttons:*\n"
                "• Link to websites, documentation, or web apps\n"
                "• Direct users to external resources\n"
                "• Drive traffic to specific landing pages\n"
                "• Provide easy access to support or contact forms\n\n"
                "💡 *Pro tip*: CTA buttons are great for bridging WhatsApp conversations with web experiences!"
            )

            await self.messenger.send_text(recipient=user_id, text=explanation_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "text", "/cta")

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ CTA command processed in {processing_time}ms")

            return {
                "success": True,
                "command": "/cta",
                "cta_sent": True,
                "url": "https://wappa.mimeia.com/docs",
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Error handling /cta command: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def handle_location_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /location command - sends predefined location.

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"📍 Processing /location command from {user_id}")

            # Predefined coordinates (Bogotá, Colombia)
            latitude = 4.616738
            longitude = -74.089853
            location_name = "Bogotá, Colombia"
            location_address = "Bogotá D.C., Colombia"

            # Send location message
            location_result = await self.messenger.send_location(
                latitude=latitude,
                longitude=longitude,
                recipient=user_id,
                name=location_name,
                address=location_address,
                reply_to_message_id=message_id,
            )

            if not location_result.success:
                self.logger.error(f"Failed to send location: {location_result.error}")
                return {"success": False, "error": "Failed to send location"}

            # Send follow-up explanation
            explanation_text = (
                f"📍 *Location Demo*\n\n"
                f"✅ *Location sent:*\n"
                f"• *Name*: {location_name}\n"
                f"• *Address*: {location_address}\n"
                f"• *Coordinates*: {latitude}, {longitude}\n"
                f"• *Maps Link*: @{latitude},{longitude},13.75z\n\n"
                f"🗺️ *About location messages:*\n"
                f"• Recipients can tap to open in Maps app\n"
                f"• Shows location name and address if provided\n"
                f"• Displays a map preview in the chat\n"
                f"• Useful for sharing business locations, meeting points, etc.\n\n"
                f"💡 *Pro tip*: Location messages are perfect for businesses to share their address with customers!"
            )

            await self.messenger.send_text(recipient=user_id, text=explanation_text)

            # Update user activity
            await self.cache_helper.update_user_activity(user_id, "text", "/location")

            processing_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ Location command processed in {processing_time}ms")

            return {
                "success": True,
                "command": "/location",
                "location_sent": True,
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "location_name": location_name,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(
                f"❌ Error handling /location command: {e}", exc_info=True
            )
            return {"success": False, "error": str(e)}

    async def handle_template_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /template command - explains template state demonstration.

        This command does NOT create state. State is created by template API
        when state_config is provided in the request.

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"📋 Processing /template command for user {user_id}")

            instructions = (
                "📬 *Template State Demo Guide*\n\n"
                "This demo shows how WhatsApp templates can trigger interactive state handlers.\n\n"
                "*How to Send a Template with State:*\n\n"
                "Use the API endpoint with `state_config` parameter:\n"
                "`POST /api/whatsapp/templates/send-text`\n\n"
                "*Example JSON:*\n"
                "```json\n"
                "{\n"
                '  "recipient": "your_phone_number",\n'
                '  "template_name": "hello_world",\n'
                '  "language": {"code": "en_US"},\n'
                '  "body_parameters": [{"type": "text", "text": "John"}],\n'
                '  "state_config": {\n'
                '    "state_value": "example",\n'
                '    "ttl_seconds": 1800,\n'
                '    "initial_context": {}\n'
                "  }\n"
                "}\n"
                "```\n\n"
                "*What Happens Next:*\n\n"
                "1️⃣ Template is sent to you via WhatsApp\n"
                "2️⃣ State `template-example` is created (30 min TTL)\n"
                "3️⃣ Any message you send triggers template echo\n"
                "4️⃣ Type */EXIT* to leave the demo\n\n"
                "*Template Types Supported:*\n"
                "• `/send-text` - Text templates\n"
                "• `/send-media` - Media templates (image/video/document)\n"
                "• `/send-location` - Location templates\n\n"
                "💡 *Tip:* Visit `/docs` for interactive API documentation\n\n"
                "Ready to try? Send a template with `state_value: example`! ✨"
            )

            await self.messenger.send_text(
                text=instructions,
                recipient=user_id,
                reply_to_message_id=message_id,
            )

            await self.cache_helper.update_user_activity(
                user_id=user_id,
                message_type="command",
                command="/template",
            )

            processing_time = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "command": "/template",
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(
                f"❌ Error handling /template command: {e}", exc_info=True
            )
            return {"success": False, "error": str(e)}

    async def handle_api_stats_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /API-STATS command - displays comprehensive API activity statistics.

        Shows:
        - Global API message statistics
        - Message type breakdown
        - Per-user activity logs
        - Recent message history

        Args:
            webhook: IncomingMessageWebhook with command
            user_profile: User profile for tracking

        Returns:
            Result dictionary with operation status
        """
        try:
            from datetime import UTC, datetime

            start_time = time.time()

            user_id = webhook.user.user_id
            message_id = webhook.message.message_id

            self.logger.info(f"📊 Processing /API-STATS command for user {user_id}")

            # Get global statistics
            stats = await self.cache_helper.get_api_message_statistics()

            # Get all user activities
            user_activities = await self.cache_helper.get_all_user_api_activities()
            user_activities.sort(key=lambda a: a.messages_received, reverse=True)

            # Get recent history
            recent_history = await self.cache_helper.get_api_message_history(limit=10)

            # Build stats message
            stats_message = (
                "📊 *API Activity Statistics*\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "*Global Statistics*\n"
                f"• Total messages: {stats.total_messages_sent}\n"
                f"• Successful: {stats.successful_sends} ✅\n"
                f"• Failed: {stats.failed_sends} ❌\n"
                f"• Success rate: {stats.success_rate:.1f}%\n"
                f"• Unique recipients: {stats.total_recipients}\n\n"
            )

            # Message type breakdown
            if stats.message_type_counts:
                stats_message += "*📈 Message Type Breakdown*\n"
                # Sort by count (descending)
                sorted_types = sorted(
                    stats.message_type_counts.items(), key=lambda x: x[1], reverse=True
                )
                for msg_type, count in sorted_types[:10]:  # Top 10
                    stats_message += f"• {msg_type}: {count}\n"
                stats_message += "\n"

            if stats.first_message_sent:
                stats_message += (
                    f"*🕐 Timeline*\n"
                    f"• First: {stats.first_message_sent.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"• Last: {stats.last_message_sent.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                )

            # User activity logs
            stats_message += "━━━━━━━━━━━━━━━━━━━━\n"
            stats_message += f"*👥 User Activity* ({len(user_activities)} users)\n\n"

            if user_activities:
                for i, activity in enumerate(user_activities[:10], 1):
                    stats_message += (
                        f"{i}. *User:* `{activity.user_id[-10:]}`\n"
                        f"   • Messages: {activity.messages_received} 📬\n"
                    )
                    if activity.last_message_received:
                        stats_message += f"   • Last: {activity.last_message_received.strftime('%Y-%m-%d %H:%M')}\n"
                    stats_message += "\n"

                if len(user_activities) > 10:
                    stats_message += (
                        f"_...and {len(user_activities) - 10} more users_\n\n"
                    )
            else:
                stats_message += "_No user activity yet_\n\n"

            # Recent history
            stats_message += "━━━━━━━━━━━━━━━━━━━━\n"
            stats_message += "*📜 Recent Messages* (last 10)\n\n"

            if recent_history:
                for i, entry in enumerate(recent_history, 1):
                    status_icon = "✅" if entry.success else "❌"
                    stats_message += (
                        f"{i}. {status_icon} *{entry.message_type}*\n"
                        f"   • To: `{entry.recipient[-10:]}`\n"
                        f"   • Time: {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    )
                    if not entry.success and entry.error:
                        stats_message += f"   • Error: {entry.error[:50]}...\n"
                    stats_message += "\n"
            else:
                stats_message += "_No history yet_\n\n"

            stats_message += "━━━━━━━━━━━━━━━━━━━━\n"
            stats_message += (
                f"*Generated:* {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            # Send stats message
            await self.messenger.send_text(
                text=stats_message,
                recipient=user_id,
                reply_to_message_id=message_id,
            )

            await self.cache_helper.update_user_activity(
                user_id=user_id,
                message_type="command",
                command="/API-STATS",
            )

            processing_time = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "command": "/API-STATS",
                "total_users": len(user_activities),
                "total_messages": stats.total_messages_sent,
                "processing_time_ms": processing_time,
            }

        except Exception as e:
            self.logger.error(f"❌ Failed to generate API stats: {e}", exc_info=True)

            await self.messenger.send_text(
                text=f"⚠️ Failed to generate API statistics.\n\nError: {str(e)}",
                recipient=user_id,
            )

            processing_time = int((time.time() - start_time) * 1000)

            return {
                "success": False,
                "command": "/API-STATS",
                "error": str(e),
                "processing_time_ms": processing_time,
            }

    async def handle_docs_command(
        self, webhook: IncomingMessageWebhook, user_profile: UserProfile
    ) -> dict[str, any]:
        """
        Handle /docs command - provides API documentation links and information.
        """
        start_time = time.time()
        user_id = webhook.user.user_id

        self.logger.info(f"📚 Processing /docs command for user {user_id}")

        docs_info = (
            "📚 *Wappa Framework Documentation*\n\n"
            "🌐 *Interactive API Documentation:*\n"
            "Visit the Swagger UI for complete API reference:\n"
            "`http://localhost:8000/docs`\n\n"
            "📖 *Main Endpoints:*\n\n"
            "*WhatsApp Messaging:*\n"
            "• `/api/whatsapp/messages/*` - Send messages\n"
            "• `/api/whatsapp/templates/*` - Send templates\n"
            "• `/api/whatsapp/interactive/*` - Interactive messages\n\n"
            "*Webhooks:*\n"
            "• `/webhook/messenger/{tenant_id}/whatsapp` - Receive webhooks\n\n"
            "💡 *Template State Example:*\n"
            "Use `/template` command to learn how to send templates with state handlers\n\n"
            "📊 *Statistics:*\n"
            "Use `/api-stats` to view comprehensive API activity\n\n"
            "🚀 *Getting Started:*\n"
            "1. Visit `/docs` in your browser\n"
            "2. Explore the available endpoints\n"
            "3. Test API calls using the Swagger UI\n"
            "4. Check `/template` for state handler examples\n\n"
            "Need help? Ask any question about the Wappa framework!"
        )

        await self.messenger.send_text(
            text=docs_info,
            recipient=user_id,
            reply_to_message_id=webhook.message.message_id,
        )

        await self.cache_helper.update_user_activity(
            user_id=user_id,
            message_type="command",
            command="/docs",
        )

        processing_time = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "command": "/docs",
            "processing_time_ms": processing_time,
        }


# Command mapping for easy lookup
COMMAND_HANDLERS = {
    "/button": "handle_button_command",
    "/list": "handle_list_command",
    "/cta": "handle_cta_command",
    "/location": "handle_location_command",
    "/template": "handle_template_command",
    "/api-stats": "handle_api_stats_command",
    "/docs": "handle_docs_command",
}


# Convenience functions for direct use
async def handle_command(
    command: str,
    webhook: IncomingMessageWebhook,
    user_profile: UserProfile,
    messenger,
    cache_factory,
    logger,
) -> dict[str, any]:
    """
    Handle command based on command string (convenience function).

    Args:
        command: Command string (e.g., "/button")
        webhook: IncomingMessageWebhook with command
        user_profile: User profile for tracking
        messenger: IMessenger instance
        cache_factory: Cache factory
        logger: Logger instance

    Returns:
        Result dictionary
    """
    handlers = CommandHandlers(messenger, cache_factory, logger)
    command_lower = command.lower()

    if command_lower == "/button":
        return await handlers.handle_button_command(webhook, user_profile)
    elif command_lower == "/list":
        return await handlers.handle_list_command(webhook, user_profile)
    elif command_lower == "/cta":
        return await handlers.handle_cta_command(webhook, user_profile)
    elif command_lower == "/location":
        return await handlers.handle_location_command(webhook, user_profile)
    elif command_lower == "/template":
        return await handlers.handle_template_command(webhook, user_profile)
    elif command_lower == "/api-stats":
        return await handlers.handle_api_stats_command(webhook, user_profile)
    elif command_lower == "/docs":
        return await handlers.handle_docs_command(webhook, user_profile)
    else:
        logger.warning(f"Unsupported command: {command}")
        return {"success": False, "error": f"Unsupported command: {command}"}


def is_special_command(text: str) -> bool:
    """
    Check if text is a special command.

    Args:
        text: Message text to check

    Returns:
        True if it's a special command, False otherwise
    """
    text_lower = text.strip().lower()
    return text_lower in [
        "/button",
        "/list",
        "/cta",
        "/location",
        "/template",
        "/api-stats",
        "/docs",
    ]


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
