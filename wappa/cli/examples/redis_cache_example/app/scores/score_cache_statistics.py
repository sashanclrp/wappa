"""
Cache Statistics Score - Single Responsibility: Redis cache monitoring and statistics.

This module handles all cache statistics operations including:
- Cache hit/miss tracking
- Cache performance metrics
- /STATS command processing
- Cache health monitoring
"""

from datetime import datetime

from wappa.webhooks import IncomingMessageWebhook

from ..models.redis_demo_models import CacheStats, MessageLog, StateHandler, User
from ..utils.message_utils import extract_command_from_message, extract_user_data
from .constants import MESSAGE_HISTORY_TABLE, WAPPA_HANDLER
from .score_base import ScoreBase


class CacheStatisticsScore(ScoreBase):
    """
    Handles cache statistics monitoring and reporting operations.

    Follows Single Responsibility Principle by focusing only
    on cache performance monitoring and statistics.
    """

    async def can_handle(self, webhook: IncomingMessageWebhook) -> bool:
        """
        This score handles /STATS command specifically.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if this is a /STATS command
        """
        message_text = webhook.get_message_text()
        if not message_text:
            return False

        command, _ = extract_command_from_message(message_text.strip())
        return command == "/STATS"

    async def process(self, webhook: IncomingMessageWebhook) -> bool:
        """
        Process cache statistics request.

        Args:
            webhook: Incoming message webhook

        Returns:
            True if processing was successful
        """
        if not await self.validate_dependencies():
            return False

        try:
            await self._handle_stats_request(webhook)
            self._record_processing(success=True)
            return True

        except Exception as e:
            await self._handle_error(e, "cache_statistics_processing")
            return False

    async def _handle_stats_request(self, webhook: IncomingMessageWebhook) -> None:
        """
        Handle /STATS command to show cache statistics.

        Args:
            webhook: Incoming message webhook
        """
        try:
            user_data = extract_user_data(webhook)
            user_id = user_data["user_id"]

            # Collect statistics from all cache layers
            stats = await self._collect_cache_statistics()

            # Generate statistics report
            stats_message = self._format_statistics_message(stats)

            # Mark message as read with typing indicator first
            await self.messenger.mark_as_read(
                message_id=webhook.message.message_id, typing=True
            )

            # Send statistics to user
            result = await self.messenger.send_text(
                recipient=user_id,
                text=stats_message,
                reply_to_message_id=webhook.message.message_id,
            )

            if result.success:
                self.logger.info(f"✅ Cache statistics sent to {user_id}")
            else:
                self.logger.error(f"❌ Failed to send statistics: {result.error}")

        except Exception as e:
            self.logger.error(f"Error handling stats request: {e}")
            raise

    async def _collect_cache_statistics(self) -> CacheStats:
        """
        Collect real-time cache statistics by querying actual cached data.

        Queries:
        - User cache: User profile and message count
        - Table cache: Message history entries
        - State cache: Active WAPPA state

        Returns:
            CacheStats object with real metrics from cache layers
        """
        stats = CacheStats()
        stats.cache_type = "Redis"
        stats.last_updated = datetime.utcnow()

        try:
            # ---- Query User Cache ----
            # Check if we have a cached user profile for the current user
            try:
                user_profile = await self.user_cache.get(models=User)
                if user_profile:
                    stats.user_cache_hits = 1
                    stats.total_operations = user_profile.message_count
                    self.logger.debug(
                        f"📊 User profile found: {user_profile.message_count} messages"
                    )
                else:
                    stats.user_cache_misses = 1
                    self.logger.debug("📊 No user profile in cache")
            except Exception as e:
                self.logger.debug(f"📊 User cache query error: {e}")
                stats.user_cache_misses = 1

            # ---- Query Table Cache (Message History) ----
            # Get message count from the current user's message history
            try:
                # Get user_id from cache_factory context
                user_id = self.cache_factory.user_id
                message_log = await self.table_cache.get(
                    MESSAGE_HISTORY_TABLE, user_id, models=MessageLog
                )
                if message_log:
                    stats.table_cache_entries = message_log.get_message_count()
                    self.logger.debug(
                        f"📊 Message history found: {stats.table_cache_entries} entries"
                    )
                else:
                    stats.table_cache_entries = 0
                    self.logger.debug("📊 No message history in cache")
            except Exception as e:
                self.logger.debug(f"📊 Table cache query error: {e}")
                stats.table_cache_entries = 0

            # ---- Query State Cache ----
            # Check if current user has an active WAPPA state
            try:
                state = await self.state_cache.get(WAPPA_HANDLER, models=StateHandler)
                if state and state.is_wappa:
                    stats.state_cache_active = 1
                    self.logger.debug("📊 Active WAPPA state found")
                else:
                    stats.state_cache_active = 0
                    self.logger.debug("📊 No active WAPPA state")
            except Exception as e:
                self.logger.debug(f"📊 State cache query error: {e}")
                stats.state_cache_active = 0

            # ---- Connection Health Check ----
            # If we got here without major exceptions, connection is healthy
            stats.connection_status = "Connected"
            stats.is_healthy = True

            self.logger.info(
                f"📊 Cache statistics collected: "
                f"user_hits={stats.user_cache_hits}, "
                f"messages={stats.table_cache_entries}, "
                f"active_states={stats.state_cache_active}"
            )
            return stats

        except Exception as e:
            self.logger.error(f"Error collecting cache statistics: {e}")
            # Return error stats
            error_stats = CacheStats()
            error_stats.cache_type = "Redis (Error)"
            error_stats.connection_status = f"Collection Error: {str(e)}"
            error_stats.is_healthy = False
            error_stats.errors = 1
            return error_stats

    def _format_statistics_message(self, stats: CacheStats) -> str:
        """
        Format cache statistics for user display.

        Args:
            stats: CacheStats object with collected metrics

        Returns:
            Formatted statistics message
        """
        try:
            health_icon = "🟢" if stats.is_healthy else "🔴"
            user_status = "✅ Found" if stats.user_cache_hits else "❌ Not found"
            state_status = "🔔 Active" if stats.state_cache_active else "💤 Inactive"

            message = [
                "📊 *Cache Statistics Report*\n\n",
                f"{health_icon} *Connection*: {stats.connection_status}\n",
                f"⚙️ *Cache Type*: {stats.cache_type}\n",
                f"🕐 *Checked At*: {stats.last_updated.strftime('%H:%M:%S')}\n\n",
                # Your data section
                "*📦 Your Cached Data:*\n",
                f"• User Profile: {user_status}\n",
                f"• Messages Logged: {stats.table_cache_entries}\n",
                f"• Total Messages Sent: {stats.total_operations}\n",
                f"• WAPPA State: {state_status}\n\n",
                # Performance indicators
                "*⚡ System Health:*\n",
                f"• Status: {'🟢 Healthy' if stats.is_healthy else '🔴 Unhealthy'}\n",
                f"• Errors: {stats.errors}\n\n",
                # Tips for users
                "*💡 Available Commands:*\n",
                "• `/HISTORY` - View message history\n",
                "• `/WAPPA` - Enter WAPPA state\n",
                "• `/EXIT` - Exit WAPPA state\n",
                "• `/STATS` - View these statistics",
            ]

            return "".join(message)

        except Exception as e:
            self.logger.error(f"Error formatting statistics message: {e}")
            return (
                "📊 Cache Statistics\n\n"
                f"❌ Error formatting statistics: {str(e)}\n\n"
                "Please try again or contact support if the issue persists."
            )

    async def get_cache_health(self) -> dict:
        """
        Get cache health status (for other score modules).

        Returns:
            Dictionary with cache health information
        """
        try:
            stats = await self._collect_cache_statistics()
            return {
                "healthy": stats.is_healthy,
                "status": stats.connection_status,
                "cache_type": stats.cache_type,
            }
        except Exception as e:
            self.logger.error(f"Error getting cache health: {e}")
            return {
                "healthy": False,
                "status": f"Health Check Error: {str(e)}",
                "cache_type": "Unknown",
            }
