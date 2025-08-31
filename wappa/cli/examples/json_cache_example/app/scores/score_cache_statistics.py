"""
Cache Statistics Score - Single Responsibility: JSON cache monitoring and statistics.

This module handles all cache statistics operations including:
- Cache hit/miss tracking
- Cache performance metrics
- /STATS command processing
- Cache health monitoring
"""

from wappa.webhooks import IncomingMessageWebhook

from ..models.json_demo_models import CacheStats
from ..utils.message_utils import extract_command_from_message, extract_user_data
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
        Get or create cache statistics from table cache (persistent storage).

        Returns:
            CacheStats object from table cache or newly created
        """
        try:
            # Use table cache to store/retrieve statistics (proper table key format)
            # table_name:pkid format as required by table cache
            stats_key = self.table_cache.create_table_key("cache_statistics", "global")

            # Try to get existing stats from table cache
            existing_stats = await self.table_cache.get(stats_key, models=CacheStats)

            if existing_stats:
                # Update existing stats
                stats = existing_stats
                stats.total_operations += 1  # Increment operation count
                stats.last_updated = stats.last_updated  # Will auto-update via Pydantic
                self.logger.debug(
                    "📊 Retrieved existing cache statistics from table cache"
                )
            else:
                # Create new stats
                stats = CacheStats()
                stats.cache_type = "JSON"
                stats.total_operations = 1
                self.logger.info("📊 Created new cache statistics in table cache")

            # Test cache connectivity using a simple operation
            try:
                # Test connectivity by creating a temporary data entry
                test_data = {
                    "test": "connectivity_check",
                    "timestamp": str(stats.last_updated),
                }
                test_key = "connectivity_test"

                # Store test data in user_cache
                await self.user_cache.set(test_key, test_data, ttl=5)
                test_result = await self.user_cache.get(test_key)

                if (
                    test_result
                    and isinstance(test_result, dict)
                    and test_result.get("test") == "connectivity_check"
                ):
                    stats.connection_status = "File System"
                    stats.is_healthy = True
                    # Clean up test key
                    await self.user_cache.delete(test_key)
                    self.logger.debug("✅ Cache connectivity test passed")
                else:
                    stats.connection_status = "File System Issues"
                    stats.is_healthy = False
                    stats.errors += 1
                    self.logger.warning(
                        f"⚠️ Cache connectivity test failed: got {test_result}"
                    )

            except Exception as cache_error:
                self.logger.error(f"Cache connectivity test failed: {cache_error}")
                stats.connection_status = f"Error: {str(cache_error)}"
                stats.is_healthy = False
                stats.errors += 1

            # Store updated statistics in table cache (persistent like message history)
            await self.table_cache.set(stats_key, stats)

            self.logger.info(
                f"📊 Cache statistics updated in table cache: {stats.connection_status}"
            )
            return stats

        except Exception as e:
            self.logger.error(f"Error collecting cache statistics: {e}")
            # Return minimal error stats (don't store errors)
            error_stats = CacheStats()
            error_stats.cache_type = "JSON (Error)"
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

            message = [
                "📊 *Cache Statistics Report*\n",
                f"{health_icon} *Cache Status*: {stats.connection_status}\n",
                f"⚙️ *Cache Type*: {stats.cache_type}\n",
                f"📈 *Total Operations*: {stats.total_operations}\n",
                f"❌ *Errors*: {stats.errors}\n",
                f"🕐 *Last Updated*: {stats.last_updated.strftime('%H:%M:%S')}\n\n",
                # Cache metrics
                "*Cache Metrics:*\n",
                f"• User Cache Hits: {stats.user_cache_hits}\n",
                f"• User Cache Misses: {stats.user_cache_misses}\n",
                f"• Table Entries: {stats.table_cache_entries}\n",
                f"• Active States: {stats.state_cache_active}\n\n",
                # Performance indicators
                "*Performance:*\n",
                f"• Health: {'🟢 Healthy' if stats.is_healthy else '🔴 Unhealthy'}\n",
                f"• Connection: {stats.connection_status}\n\n",
                # Tips for users
                "*Available Commands:*\n",
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
