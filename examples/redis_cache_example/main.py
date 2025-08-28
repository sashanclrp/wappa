"""
Redis Cache Demo for Wappa Framework - SIMPLIFIED VERSION

This example demonstrates the NEW simplified way to run Wappa apps in development mode.
No more complex create_fastapi_app() boilerplate needed!

SETUP REQUIRED:
1. Create a .env file with your WhatsApp Business API credentials:
    WP_ACCESS_TOKEN=your_access_token_here
    WP_PHONE_ID=your_phone_number_id_here
    WP_BID=your_business_id_here

2. Set up Redis:
    REDIS_URL=redis://localhost:6379

DEMO FEATURES:
- User data extraction and caching from incoming webhooks
- Message history logging to table cache (every message stored per user with timestamps)
- BaseModel auto-serialization: Redis handles Pydantic model serialization/deserialization
- Table cache key management: Uses create_table_key() helper for proper key formatting
- State management for /WAPPA command flow:
  * Send "/WAPPA" to activate state
  * User gets "You are in wappa state, to exit wappa state write /EXIT"
  * All messages replied with "Hola Wapp@ ;)"
  * Send "/EXIT" to deactivate state and cleanup cache
- Message history retrieval:
  * Send "/HISTORY" to see your last 20 messages with timestamps

DEVELOPMENT MODES:
1. Direct Python: python main_simplified.py (uses settings.is_development for mode)
2. FastAPI-style: uvicorn main_simplified:app.asgi --reload (clean, no boilerplate)  
3. Wappa CLI: wappa dev main_simplified.py (batteries-included convenience)

The new .asgi property approach eliminates all threading complexity!
"""


# Import our demo models (handle both direct run and CLI execution)
import sys
from pathlib import Path

# Add the example directory to Python path for local imports
example_dir = Path(__file__).parent
if str(example_dir) not in sys.path:
    sys.path.insert(0, str(example_dir))

from models.redis_demo_models import CacheStats, MessageLog, StateHandler, User

# Import from the installed wappa package
from wappa import Wappa, WappaEventHandler, __version__
from wappa.core.config.settings import settings
from wappa.domain.interfaces.cache_interface import ICache
from wappa.webhooks import ErrorWebhook, IncomingMessageWebhook, StatusWebhook


class RedisCacheDemoHandler(WappaEventHandler):
    """
    Comprehensive Redis cache demonstration handler.
    
    Demonstrates all three cache types with BaseModel auto-serialization:
    - user_cache: User profile data (User model)
    - table_cache: Message history logging (MessageLog with MessageHistory list)
    - state_handler: /WAPPA command state management (StateHandler model)
    
    BaseModel Pattern:
    - cache.get(key, models=BaseModelClass) returns BaseModel instance
    - cache.set(key, pydantic_model) automatically serializes
    - No need for manual model_dump() or dict construction
    
    Table Cache Key Helper:
    - table_cache.create_table_key(table_name, pkid) for proper formatting
    - Automatic validation and sanitization of table keys
    - Clear error messages for invalid key formats
    """

    def __init__(self):
        """Initialize handler with cache statistics tracking."""
        super().__init__()

        # Initialize cache statistics
        self._cache_stats = CacheStats()

        # Cache instances (will be created from factory per-request)
        self._user_cache: ICache | None = None
        self._table_cache: ICache | None = None
        self._state_cache: ICache | None = None

        self.logger.info("🚀 RedisCacheDemoHandler initialized - Redis caches will be created per-request")

    async def process_message(self, webhook: IncomingMessageWebhook) -> None:
        """
        Process incoming messages with comprehensive cache demonstration.
        
        Flow:
        1. Validate dependencies and setup caches
        2. Extract and cache user data
        3. Log message to table cache
        4. Handle /WAPPA and /EXIT commands
        5. Send appropriate responses
        """
        try:
            # 1. Validate dependencies and setup caches
            if not await self._setup_caches(webhook):
                return

            # 2. Extract user data and update user cache
            user_data = await self._handle_user_cache(webhook)
            if not user_data:
                return

            # 3. Log message to table cache
            await self._handle_message_logging(webhook)

            # 4. Check for special commands and handle state
            message_text = webhook.get_message_text().strip()

            if message_text.upper() == "/WAPPA":
                await self._handle_wappa_activation(webhook, user_data)
            elif message_text.upper() == "/EXIT":
                await self._handle_wappa_exit(webhook, user_data)
            elif message_text.upper() == "/HISTORY":
                await self._handle_history_request(webhook, user_data)
            else:
                # Check if user is in WAPPA state
                await self._handle_normal_message(webhook, user_data, message_text)

            # 5. Log cache statistics
            await self._log_cache_statistics()

        except Exception as e:
            self.logger.error(f"❌ Error processing message: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _setup_caches(self, webhook: IncomingMessageWebhook) -> bool:
        """Setup cache instances from injected cache factory."""
        if not self.validate_dependencies():
            self.logger.error("❌ Dependencies not properly injected")
            return False

        if not self.cache_factory:
            self.logger.error("❌ Cache factory not injected - Redis caching unavailable")
            return False

        try:
            # Create cache instances for this request
            self._user_cache = self.cache_factory.create_user_cache()
            self._table_cache = self.cache_factory.create_table_cache()
            self._state_cache = self.cache_factory.create_state_cache()

            self.logger.info("✅ Cache instances created: user, table, state")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to create cache instances: {e}", exc_info=True)
            self._cache_stats.record_error()
            return False

    async def _handle_user_cache(self, webhook: IncomingMessageWebhook) -> User | None:
        """Handle user data caching and retrieval using BaseModel pattern."""
        try:
            user_id = webhook.user.user_id
            user_name = webhook.user.profile_name

            # Try to get existing user data with BaseModel deserialization
            user = await self._user_cache.get("user_profile", models=User)

            if user:
                # User exists, update data
                user.increment_message_count()

                # Update name if provided and different
                if user_name and user.user_name != user_name:
                    user.user_name = user_name

                self._cache_stats.record_user_hit()
                self.logger.info(f"👤 User cache HIT: {user_id} (messages: {user.message_count})")

            else:
                # New user, create profile
                user = User(
                    phone_number=user_id,
                    user_name=user_name,
                    message_count=1
                )

                self._cache_stats.record_user_miss()
                self.logger.info(f"👤 User cache MISS: Creating new profile for {user_id}")

            # Save updated user data (Redis auto-serializes Pydantic models)
            await self._user_cache.set("user_profile", user, ttl=86400)  # 24 hours

            return user

        except Exception as e:
            self.logger.error(f"❌ User cache error: {e}", exc_info=True)
            self._cache_stats.record_error()
            return None

    async def _handle_message_logging(self, webhook: IncomingMessageWebhook) -> None:
        """Log every message to user's message history using BaseModel pattern."""
        try:
            user_id = webhook.user.user_id
            message_text = webhook.get_message_text()
            message_type = webhook.get_message_type_name()
            tenant_id = webhook.tenant.get_tenant_key()

            # Generate properly formatted table cache key using the helper method
            log_key = self._table_cache.create_table_key("msg_history", user_id)

            # Try to get existing message history with BaseModel deserialization
            message_log = await self._table_cache.get(log_key, models=MessageLog)

            if message_log:
                # User has existing history, update it
                self.logger.debug(f"📝 Found existing history for {user_id} ({message_log.get_message_count()} messages)")
            else:
                # New user, create new message history
                message_log = MessageLog(
                    user_id=user_id,
                    tenant_id=tenant_id
                )
                self.logger.info(f"📝 Creating new message history for {user_id}")

            # Add the new message to history
            message_content = message_text or f"[{message_type.upper()} MESSAGE]"
            message_log.add_message(message_content, message_type)

            # Store back to Redis using Pydantic auto-serialization
            await self._table_cache.set(log_key, message_log, ttl=86400)  # 7 days

            self._cache_stats.record_table_entry()
            self.logger.info(
                f"📝 Message added to history: {user_id} "
                f"(total: {message_log.get_message_count()} messages)"
            )

        except Exception as e:
            self.logger.error(f"❌ Message logging error: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _handle_wappa_activation(self, webhook: IncomingMessageWebhook, user: User) -> None:
        """Handle /WAPPA command activation."""
        try:
            user_id = webhook.user.user_id

            # Create and save WAPPA state
            state = StateHandler()
            state.activate_wappa()

            # Store state using Redis auto-serialization
            await self._state_cache.set("wappa_state", state, ttl=3600)  # 1 hour

            self._cache_stats.record_state_activation()

            # Send activation message
            activation_message = (
                "🎉 You are in wappa state, to exit wappa state write /EXIT\n\n"
                "✨ While in WAPPA state:\n"
                "• I'll respond with 'Hola Wapp@ ;)' to all your messages\n"
                "• Your state is cached in Redis\n"
                "• Write /EXIT to leave WAPPA state"
            )

            result = await self.messenger.send_text(
                recipient=user_id,
                text=activation_message,
                reply_to_message_id=webhook.message.message_id
            )

            if result.success:
                self.logger.info(f"✅ WAPPA state activated for {user_id}")
            else:
                self.logger.error(f"❌ Failed to send WAPPA activation message: {result.error}")

        except Exception as e:
            self.logger.error(f"❌ WAPPA activation error: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _handle_wappa_exit(self, webhook: IncomingMessageWebhook, user: User) -> None:
        """Handle /EXIT command deactivation."""
        try:
            user_id = webhook.user.user_id

            # Check if user has WAPPA state
            existing_state_data = await self._state_cache.get("wappa_state")

            if existing_state_data:
                state = StateHandler(**existing_state_data)

                if state.is_wappa:
                    # Calculate how long they were in WAPPA state
                    duration = state.get_state_duration()
                    command_count = state.command_count

                    # Deactivate and delete state
                    await self._state_cache.delete("wappa_state")
                    self._cache_stats.record_state_deactivation()

                    # Send exit message
                    exit_message = (
                        "👋 You are no longer in wappa state!\n\n"
                        f"📊 Session Summary:\n"
                        f"• Duration: {duration} seconds\n"
                        f"• Commands processed: {command_count}\n"
                        f"• State cleared from Redis cache"
                    )

                    result = await self.messenger.send_text(
                        recipient=user_id,
                        text=exit_message,
                        reply_to_message_id=webhook.message.message_id
                    )

                    if result.success:
                        self.logger.info(f"✅ WAPPA state deactivated for {user_id} (duration: {duration}s)")
                    else:
                        self.logger.error(f"❌ Failed to send WAPPA exit message: {result.error}")
                else:
                    # State exists but not active
                    await self.messenger.send_text(
                        recipient=user_id,
                        text="❓ You are not currently in WAPPA state. Send /WAPPA to activate it.",
                        reply_to_message_id=webhook.message.message_id
                    )
            else:
                # No state found
                await self.messenger.send_text(
                    recipient=user_id,
                    text="❓ No WAPPA state found. Send /WAPPA to activate it.",
                    reply_to_message_id=webhook.message.message_id
                )

        except Exception as e:
            self.logger.error(f"❌ WAPPA exit error: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _handle_history_request(self, webhook: IncomingMessageWebhook, user: User) -> None:
        """Handle /HISTORY command to show user's message history."""
        try:
            user_id = webhook.user.user_id

            # Get user's message history from table cache using helper method and BaseModel deserialization
            log_key = self._table_cache.create_table_key("msg_history", user_id)
            message_log = await self._table_cache.get(log_key, models=MessageLog)

            if message_log:
                # User has message history
                recent_messages = message_log.get_recent_messages(20)  # Get last 20 messages
                total_count = message_log.get_message_count()

                if recent_messages:
                    # Format the history message
                    history_text = f"📚 Your Message History ({total_count} total messages):\n\n"

                    for i, msg_history in enumerate(recent_messages, 1):
                        timestamp_str = msg_history.timestamp.strftime("%Y-%m-%d %H:%M")
                        msg_type = f"[{msg_history.message_type.upper()}]" if msg_history.message_type != "text" else ""
                        history_text += f"{i:2d}. {timestamp_str} {msg_type} {msg_history.message}\n"

                    if total_count > 20:
                        history_text += f"\n... showing last 20 of {total_count} messages"

                    # Send the history to the user
                    result = await self.messenger.send_text(
                        recipient=user_id,
                        text=history_text,
                        reply_to_message_id=webhook.message.message_id
                    )

                    if result.success:
                        self.logger.info(f"✅ History sent to {user_id} ({total_count} messages)")
                    else:
                        self.logger.error(f"❌ Failed to send history: {result.error}")
                else:
                    # No messages in history
                    await self.messenger.send_text(
                        recipient=user_id,
                        text="📚 Your message history is empty. Start chatting to build your history!",
                        reply_to_message_id=webhook.message.message_id
                    )
            else:
                # No history found for this user
                await self.messenger.send_text(
                    recipient=user_id,
                    text="📚 No message history found. This is your first message! Welcome! 👋",
                    reply_to_message_id=webhook.message.message_id
                )

        except Exception as e:
            self.logger.error(f"❌ History request error: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _handle_normal_message(self, webhook: IncomingMessageWebhook, user: User, message_text: str) -> None:
        """Handle normal messages, checking for WAPPA state."""
        try:
            user_id = webhook.user.user_id

            # Check if user is in WAPPA state with BaseModel deserialization
            state = await self._state_cache.get("wappa_state", models=StateHandler)

            if state:

                if state.is_wappa:
                    # User is in WAPPA state, send the special response
                    state.process_command(message_text)

                    # Update state in cache using Redis auto-serialization
                    await self._state_cache.set("wappa_state", state, ttl=3600)

                    # Send WAPPA response
                    result = await self.messenger.send_text(
                        recipient=user_id,
                        text="Hola Wapp@ ;)",
                        reply_to_message_id=webhook.message.message_id
                    )

                    if result.success:
                        self.logger.info(f"✅ WAPPA response sent to {user_id} (command #{state.command_count})")
                    else:
                        self.logger.error(f"❌ Failed to send WAPPA response: {result.error}")

                    return

            # Normal message, send informational response
            info_message = (
                f"👋 Hello {user.user_name or 'there'}!\n\n"
                f"📊 Your Profile:\n"
                f"• Messages sent: {user.message_count}\n"
                f"• First seen: {user.first_seen.strftime('%Y-%m-%d %H:%M')}\n"
                f"• Last seen: {user.last_seen.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"🎯 Special Commands:\n"
                f"• Send '/WAPPA' to enter special state\n"
                f"• Send '/EXIT' to leave special state\n"
                f"• Send '/HISTORY' to see your message history\n\n"
                f"💾 This demo showcases Redis caching:\n"
                f"• User data cached in user_cache\n"
                f"• Message history stored in table_cache per user\n"
                f"• Commands tracked in state_cache"
            )

            result = await self.messenger.send_text(
                recipient=user_id,
                text=info_message,
                reply_to_message_id=webhook.message.message_id
            )

            if result.success:
                self.logger.info(f"✅ Info message sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send info message: {result.error}")

        except Exception as e:
            self.logger.error(f"❌ Normal message handling error: {e}", exc_info=True)
            self._cache_stats.record_error()

    async def _log_cache_statistics(self) -> None:
        """Log current cache statistics."""
        try:
            stats = self._cache_stats
            hit_rate = stats.get_user_hit_rate()
            error_rate = stats.get_error_rate()

            self.logger.info(
                f"📊 Cache Stats: "
                f"user_hits={stats.user_cache_hits}, "
                f"user_misses={stats.user_cache_misses}, "
                f"hit_rate={hit_rate:.1%}, "
                f"table_entries={stats.table_cache_entries}, "
                f"active_states={stats.state_cache_active}, "
                f"total_ops={stats.total_operations}, "
                f"errors={stats.errors} ({error_rate:.1%})"
            )

        except Exception as e:
            self.logger.error(f"❌ Stats logging error: {e}", exc_info=True)

    async def process_status(self, webhook: StatusWebhook) -> None:
        """Custom status processing."""
        status_value = webhook.status.value
        recipient = webhook.recipient_id

        self.logger.info(f"📊 Message status: {status_value.upper()} for {recipient}")

    async def process_error(self, webhook: ErrorWebhook) -> None:
        """Custom error processing."""
        error_count = webhook.get_error_count()
        primary_error = webhook.get_primary_error()

        self.logger.error(
            f"🚨 Platform error: {error_count} errors, "
            f"primary: {primary_error.error_code} - {primary_error.error_title}"
        )

        self._cache_stats.record_error()


# ============================================================================
# SIMPLIFIED WAPPA SETUP - NO COMPLEX BOILERPLATE NEEDED!
# ============================================================================

# Create Wappa instance at module level (required for auto-reload)
app = Wappa(cache="redis")
handler = RedisCacheDemoHandler()
app.set_event_handler(handler)

def main():
    """Main demo function."""
    print(f"🚀 Wappa v{__version__} - Redis Cache Demo (SIMPLIFIED)")
    print("=" * 60)
    print()
    print("🎯 **REDIS CACHE DEMONSTRATION:**")
    print("  • User Cache: Store user profile data")
    print("  • Table Cache: Log all incoming messages")
    print("  • State Handler: Manage /WAPPA command flow")
    print()
    print("📋 Configuration Check:")
    print(f"  • Access Token: {'✅ Set' if settings.wp_access_token else '❌ Missing'}")
    print(f"  • Phone ID: {settings.wp_phone_id if settings.wp_phone_id else '❌ Missing'}")
    print(f"  • Business ID: {'✅ Set' if settings.wp_bid else '❌ Missing'}")
    print(f"  • Redis URL: {'✅ Set' if settings.has_redis else '❌ Missing'}")
    print()

    if not settings.has_redis:
        print("❌ Redis URL not configured! Set REDIS_URL in your .env file")
        return

    print("🧪 **DEMO FEATURES:**")
    print("  1. Send any message → User data cached, message added to history")
    print("  2. Send '/WAPPA' → Enter special state")
    print("  3. Send any message → Replies 'Hola Wapp@ ;)'")
    print("  4. Send '/EXIT' → Leave special state, cache cleaned")
    print("  5. Send '/HISTORY' → See your last 20 messages with timestamps")
    print("  6. Check logs for cache operations and statistics")
    print()
    print("💎 **BASEMODEL AUTO-SERIALIZATION:**")
    print("  • cache.get(key, models=ModelClass) → Returns BaseModel instance")
    print("  • cache.set(key, pydantic_model) → Auto-serializes to Redis")
    print("  • No manual model_dump() or dict construction needed")
    print("  • Datetime, enum, and nested model support included")
    print()
    print("🔑 **TABLE CACHE KEY MANAGEMENT:**")
    print("  • table_cache.create_table_key(table_name, pkid) → Proper key format")
    print("  • Automatic key validation and sanitization")
    print("  • Clear error messages for invalid key formats")
    print("  • Example: cache.create_table_key('msg_history', user_id)")
    print()

    print("🔧 **CACHE ARCHITECTURE:**")
    print("  • user_cache (db0): User profiles with TTL 24h")
    print("  • table_cache (db2): Message history per user with TTL 7d")
    print("  • state_handler (db1): Command states with TTL 1h")
    print()

    print("🌐 Starting Redis cache demo server...")
    print("💡 Press CTRL+C to stop the server")
    print()
    print("✨ **NEW FASTAPI-STYLE APPROACH:**")
    print("  • No complex create_fastapi_app() function needed!")
    print("  • Clean .asgi property for uvicorn reload compatibility")
    print("  • Just app.run() OR uvicorn main:app.asgi --reload")
    print("  • Lifespan hooks handle async initialization")
    print("=" * 60)

    try:
        print("✅ Wappa created with automatic Redis plugin integration")
        print("✅ Wappa app configured with Redis cache handler")

        # THAT'S IT! No complex ASGI export functions needed!
        # Framework handles everything automatically
        app.run()

    except KeyboardInterrupt:
        print("\n👋 Redis cache demo stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
    finally:
        print("🏁 Redis cache demo completed")


if __name__ == "__main__":
    main()
