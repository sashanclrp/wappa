"""
Cache utilities for Redis operations in the Wappa Full Example application.

This module provides helper functions and classes for working with Redis cache,
including user management, state management, and statistics tracking.
"""

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from ..models.state_models import InteractiveState, StateType
from ..models.user_models import UserProfile

T = TypeVar("T", bound=BaseModel)


class CacheHelper:
    """Helper class for common cache operations."""

    def __init__(self, cache_factory):
        """
        Initialize CacheHelper with cache factory.

        Args:
            cache_factory: Wappa cache factory instance
        """
        self.cache_factory = cache_factory
        self._user_cache = None
        self._state_cache = None
        self._table_cache = None

    @property
    def user_cache(self):
        """Get user cache instance."""
        if not self._user_cache:
            self._user_cache = self.cache_factory.create_user_cache()
        return self._user_cache

    @property
    def state_cache(self):
        """Get state cache instance."""
        if not self._state_cache:
            self._state_cache = self.cache_factory.create_state_cache()
        return self._state_cache

    @property
    def table_cache(self):
        """Get table cache instance."""
        if not self._table_cache:
            self._table_cache = self.cache_factory.create_table_cache()
        return self._table_cache

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        """
        Get user profile from cache.

        Args:
            user_id: User phone number/ID

        Returns:
            UserProfile object or None if not found
        """
        try:
            profile_data = await self.user_cache.get(
                f"user_profile_{user_id}", models=UserProfile
            )
            return profile_data
        except Exception as e:
            print(f"Error getting user profile {user_id}: {e}")
            return None

    async def save_user_profile(
        self, user_profile: UserProfile, ttl_seconds: int = 86400
    ) -> bool:
        """
        Save user profile to cache.

        Args:
            user_profile: UserProfile object to save
            ttl_seconds: Time to live in seconds (default 24 hours)

        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = f"user_profile_{user_profile.phone_number}"
            await self.user_cache.set(cache_key, user_profile, ttl=ttl_seconds)
            return True
        except Exception as e:
            print(f"Error saving user profile {user_profile.phone_number}: {e}")
            return False

    async def get_or_create_user_profile(
        self,
        user_id: str,
        user_name: str | None = None,
        profile_name: str | None = None,
    ) -> UserProfile:
        """
        Get existing user profile or create a new one.

        Args:
            user_id: User phone number/ID
            user_name: Optional user name
            profile_name: Optional profile name

        Returns:
            UserProfile object (existing or new)
        """
        # Try to get existing profile
        profile = await self.get_user_profile(user_id)

        if profile:
            # Update profile information if provided
            profile.update_profile_info(user_name, profile_name)
            return profile
        else:
            # Create new profile
            profile = UserProfile(
                phone_number=user_id,
                user_name=user_name,
                profile_name=profile_name,
                is_first_time_user=True,
                has_received_welcome=False,
            )

            # Save new profile
            await self.save_user_profile(profile)
            return profile

    async def update_user_activity(
        self,
        user_id: str,
        message_type: str = "text",
        command: str | None = None,
        interaction_type: str | None = None,
    ) -> UserProfile | None:
        """
        Update user activity statistics.

        Args:
            user_id: User phone number/ID
            message_type: Type of message
            command: Optional command used
            interaction_type: Optional interaction type

        Returns:
            Updated UserProfile or None if error
        """
        try:
            profile = await self.get_or_create_user_profile(user_id)

            # Update message count
            profile.increment_message_count(message_type)

            # Update command usage
            if command:
                profile.increment_command_usage(command)

            # Update interactions
            if interaction_type:
                profile.increment_interactions(interaction_type)

            # Save updated profile
            await self.save_user_profile(profile)
            return profile

        except Exception as e:
            print(f"Error updating user activity {user_id}: {e}")
            return None

    async def get_user_state(
        self, user_id: str, state_type: StateType
    ) -> InteractiveState | None:
        """
        Get user interactive state.

        Args:
            user_id: User phone number/ID
            state_type: Type of state to get

        Returns:
            InteractiveState object or None if not found/expired
        """
        try:
            # Use simpler cache key format: state_{state_type}
            cache_key = f"state_{state_type.value}"

            # Import the specific state classes for proper type casting
            from ..models.state_models import ButtonState, ListState

            # Use the appropriate model class based on state type
            model_class = InteractiveState
            if state_type == StateType.BUTTON:
                model_class = ButtonState
            elif state_type == StateType.LIST:
                model_class = ListState

            state_data = await self.state_cache.get(cache_key, models=model_class)

            if state_data and state_data.is_expired():
                # Remove expired state
                await self.state_cache.delete(cache_key)
                return None

            return state_data
        except Exception as e:
            print(f"Error getting user state {state_type.value}: {e}")
            return None

    async def save_user_state(self, state: InteractiveState) -> bool:
        """
        Save user interactive state.

        Args:
            state: InteractiveState object to save

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use simpler cache key format: state_{state_type}
            cache_key = f"state_{state.state_type.value}"
            ttl = state.time_remaining_seconds()

            if ttl <= 0:
                # Don't save expired states
                return False

            await self.state_cache.set(cache_key, state, ttl=ttl)
            return True
        except Exception as e:
            print(f"Error saving user state {state.state_type.value}: {e}")
            return False

    async def remove_user_state(self, user_id: str, state_type: StateType) -> bool:
        """
        Remove user interactive state.

        Args:
            user_id: User phone number/ID
            state_type: Type of state to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use simpler cache key format: state_{state_type}
            cache_key = f"state_{state_type.value}"
            result = await self.state_cache.delete(cache_key)
            return result
        except Exception as e:
            print(f"Error removing user state {state_type.value}: {e}")
            return False

    async def cleanup_expired_states(self, batch_size: int = 100) -> int:
        """
        Cleanup expired states from cache.

        Args:
            batch_size: Number of states to check in each batch

        Returns:
            Number of expired states cleaned up
        """
        cleanup_count = 0
        try:
            # This is a simplified implementation
            # In a real implementation, you would need to scan Redis keys
            # and check expiration status

            # For now, return 0 as this requires Redis-specific commands
            return cleanup_count
        except Exception as e:
            print(f"Error during cleanup: {e}")
            return 0

    async def get_cache_statistics(self) -> dict[str, Any]:
        """
        Get cache usage statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            stats = {
                "timestamp": datetime.now().isoformat(),
                "user_cache": {
                    "type": "user_profiles",
                    "description": "User profile and activity data",
                },
                "state_cache": {
                    "type": "interactive_states",
                    "description": "Active interactive command states",
                },
                "table_cache": {
                    "type": "structured_data",
                    "description": "Structured application data",
                },
            }

            # Add cache-specific info if available
            try:
                # Try to get cache info from Redis if available
                # This would require implementing Redis-specific info commands
                pass
            except:
                pass

            return stats
        except Exception as e:
            print(f"Error getting cache statistics: {e}")
            return {"error": str(e)}

    async def store_message_history(
        self, user_id: str, message_data: dict[str, Any], max_history: int = 50
    ) -> bool:
        """
        Store message in user's history.

        Args:
            user_id: User phone number/ID
            message_data: Dictionary with message information
            max_history: Maximum number of messages to keep

        Returns:
            True if successful, False otherwise
        """
        try:
            history_key = f"history_{user_id}"

            # Get existing history
            history = await self.table_cache.get(history_key, models=list) or []

            # Add new message with timestamp
            message_entry = {**message_data, "stored_at": datetime.now().isoformat()}

            history.append(message_entry)

            # Keep only recent messages
            if len(history) > max_history:
                history = history[-max_history:]

            # Save updated history
            await self.table_cache.set(history_key, history, ttl=604800)  # 7 days
            return True

        except Exception as e:
            print(f"Error storing message history {user_id}: {e}")
            return False

    async def get_message_history(
        self, user_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Get user's message history.

        Args:
            user_id: User phone number/ID
            limit: Maximum number of messages to return

        Returns:
            List of message history entries
        """
        try:
            history_key = f"history_{user_id}"
            history = await self.table_cache.get(history_key, models=list) or []

            # Return recent messages
            return history[-limit:] if history else []

        except Exception as e:
            print(f"Error getting message history {user_id}: {e}")
            return []

    async def store_application_data(
        self, key: str, data: Any, ttl_seconds: int | None = None
    ) -> bool:
        """
        Store application-specific data.

        Args:
            key: Cache key
            data: Data to store
            ttl_seconds: Optional TTL in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.table_cache.set(key, data, ttl=ttl_seconds)
            return True
        except Exception as e:
            print(f"Error storing application data {key}: {e}")
            return False

    async def get_application_data(
        self, key: str, model_class: type[T] | None = None
    ) -> Any:
        """
        Get application-specific data.

        Args:
            key: Cache key
            model_class: Optional Pydantic model class for validation

        Returns:
            Stored data or None if not found
        """
        try:
            return await self.table_cache.get(key, models=model_class)
        except Exception as e:
            print(f"Error getting application data {key}: {e}")
            return None


class CacheKeys:
    """Centralized cache key management."""

    @staticmethod
    def user_profile(user_id: str) -> str:
        """Get cache key for user profile."""
        return f"user_profile_{user_id}"

    @staticmethod
    def user_state(user_id: str, state_type: str) -> str:
        """Get cache key for user state."""
        return f"state_{state_type}"

    @staticmethod
    def message_history(user_id: str) -> str:
        """Get cache key for message history."""
        return f"history_{user_id}"

    @staticmethod
    def user_session(user_id: str) -> str:
        """Get cache key for user session."""
        return f"session_{user_id}"

    @staticmethod
    def application_stats() -> str:
        """Get cache key for application statistics."""
        return "app_stats"

    @staticmethod
    def daily_stats(date_str: str | None = None) -> str:
        """Get cache key for daily statistics."""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        return f"daily_stats_{date_str}"


# Convenience functions for direct use
async def get_user_from_cache(cache_factory, user_id: str) -> UserProfile | None:
    """
    Get user profile from cache (convenience function).

    Args:
        cache_factory: Wappa cache factory
        user_id: User phone number/ID

    Returns:
        UserProfile or None
    """
    helper = CacheHelper(cache_factory)
    return await helper.get_user_profile(user_id)


async def save_user_to_cache(cache_factory, user_profile: UserProfile) -> bool:
    """
    Save user profile to cache (convenience function).

    Args:
        cache_factory: Wappa cache factory
        user_profile: UserProfile to save

    Returns:
        True if successful, False otherwise
    """
    helper = CacheHelper(cache_factory)
    return await helper.save_user_profile(user_profile)


async def update_user_stats(
    cache_factory, user_id: str, message_type: str = "text", command: str | None = None
) -> UserProfile | None:
    """
    Update user statistics (convenience function).

    Args:
        cache_factory: Wappa cache factory
        user_id: User phone number/ID
        message_type: Message type
        command: Optional command

    Returns:
        Updated UserProfile or None
    """
    helper = CacheHelper(cache_factory)
    return await helper.update_user_activity(user_id, message_type, command)
