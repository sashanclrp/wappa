"""
State Manager for Echo Project

Handles Redis-based state management for interactive features (buttons, lists).
Provides tenant-aware state operations with automatic TTL management.

Features:
- Button state management (10min TTL)
- List state management (10min TTL)
- Automatic state expiration and cleanup
- Tenant isolation through cache keys
- Comprehensive error handling and logging
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

from wappa.domain.interfaces.cache_interface import ICache

from constants import (
    BUTTON_STATE_TTL_SECONDS, LIST_STATE_TTL_SECONDS,
    STATE_TYPE_BUTTON, STATE_TYPE_LIST, get_state_key
)


@dataclass
class InteractiveState:
    """
    Interactive state data structure for buttons and lists.
    
    Contains all information needed to manage interactive sessions
    with automatic expiration and context preservation.
    """
    state_type: str  # "button" | "list"
    user_id: str
    created_at: str  # ISO format datetime
    expires_at: str  # ISO format datetime  
    context: Dict[str, Any]
    
    def is_expired(self) -> bool:
        """Check if this state has expired."""
        try:
            expires_at = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            return datetime.utcnow() > expires_at
        except (ValueError, AttributeError):
            return True
            
    def time_remaining_seconds(self) -> int:
        """Get remaining time in seconds before expiration."""
        try:
            expires_at = datetime.fromisoformat(self.expires_at.replace('Z', '+00:00'))
            remaining = expires_at - datetime.utcnow()
            return max(0, int(remaining.total_seconds()))
        except (ValueError, AttributeError):
            return 0
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InteractiveState':
        """Create instance from dictionary."""
        return cls(**data)


class StateManager:
    """
    Manages interactive state for buttons and lists using Redis cache.
    
    Provides high-level operations for creating, retrieving, updating,
    and cleaning up interactive states with automatic TTL management.
    """
    
    def __init__(self, state_cache: ICache, logger):
        """
        Initialize StateManager with cache and logger.
        
        Args:
            state_cache: Redis cache instance for state storage
            logger: Logger instance for debugging and monitoring
        """
        self.state_cache = state_cache
        self.logger = logger
        
    async def create_button_state(self, user_id: str, context: Dict[str, Any]) -> bool:
        """
        Create a new button state for user.
        
        Args:
            user_id: User identifier
            context: Button context data (button IDs, message info, etc.)
            
        Returns:
            True if state created successfully, False otherwise
        """
        try:
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=BUTTON_STATE_TTL_SECONDS)
            
            state = InteractiveState(
                state_type=STATE_TYPE_BUTTON,
                user_id=user_id,
                created_at=now.isoformat() + 'Z',
                expires_at=expires_at.isoformat() + 'Z',
                context=context
            )
            
            state_key = get_state_key(user_id, STATE_TYPE_BUTTON)
            
            # Store with TTL
            success = await self.state_cache.set(
                key=state_key,
                value=state.to_dict(),
                ttl=BUTTON_STATE_TTL_SECONDS
            )
            
            if success:
                self.logger.info(
                    f"🔘 Button state created for {user_id} "
                    f"(expires in {BUTTON_STATE_TTL_SECONDS}s)"
                )
            else:
                self.logger.error(f"❌ Failed to create button state for {user_id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error creating button state for {user_id}: {e}")
            return False
            
    async def create_list_state(self, user_id: str, context: Dict[str, Any]) -> bool:
        """
        Create a new list state for user.
        
        Args:
            user_id: User identifier
            context: List context data (list options, message info, etc.)
            
        Returns:
            True if state created successfully, False otherwise
        """
        try:
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=LIST_STATE_TTL_SECONDS)
            
            state = InteractiveState(
                state_type=STATE_TYPE_LIST,
                user_id=user_id,
                created_at=now.isoformat() + 'Z',
                expires_at=expires_at.isoformat() + 'Z',
                context=context
            )
            
            state_key = get_state_key(user_id, STATE_TYPE_LIST)
            
            # Store with TTL
            success = await self.state_cache.set(
                key=state_key,
                value=state.to_dict(),
                ttl=LIST_STATE_TTL_SECONDS
            )
            
            if success:
                self.logger.info(
                    f"📋 List state created for {user_id} "
                    f"(expires in {LIST_STATE_TTL_SECONDS}s)"
                )
            else:
                self.logger.error(f"❌ Failed to create list state for {user_id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error creating list state for {user_id}: {e}")
            return False
            
    async def get_user_state(self, user_id: str, state_type: str) -> Optional[InteractiveState]:
        """
        Get active state for user and type.
        
        Args:
            user_id: User identifier
            state_type: State type ("button" or "list")
            
        Returns:
            InteractiveState if found and not expired, None otherwise
        """
        try:
            state_key = get_state_key(user_id, state_type)
            
            # Get state data from cache
            state_data = await self.state_cache.get(state_key)
            
            if not state_data:
                return None
                
            # Convert to InteractiveState object
            if isinstance(state_data, dict):
                state = InteractiveState.from_dict(state_data)
            else:
                # Handle case where data might be JSON string
                try:
                    state_dict = json.loads(state_data)
                    state = InteractiveState.from_dict(state_dict)
                except (json.JSONDecodeError, TypeError):
                    self.logger.error(f"❌ Invalid state data format for {user_id}:{state_type}")
                    return None
            
            # Check if state has expired
            if state.is_expired():
                self.logger.info(f"⏰ State expired for {user_id}:{state_type}, cleaning up")
                await self.delete_user_state(user_id, state_type)
                return None
                
            self.logger.debug(
                f"✅ Active {state_type} state found for {user_id} "
                f"(expires in {state.time_remaining_seconds()}s)"
            )
            
            return state
            
        except Exception as e:
            self.logger.error(f"❌ Error getting state for {user_id}:{state_type}: {e}")
            return None
            
    async def update_user_state(self, user_id: str, state_type: str, 
                                context_updates: Dict[str, Any]) -> bool:
        """
        Update context for existing user state.
        
        Args:
            user_id: User identifier
            state_type: State type ("button" or "list")
            context_updates: Context updates to merge
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Get current state
            current_state = await self.get_user_state(user_id, state_type)
            
            if not current_state:
                self.logger.warning(f"⚠️ No active {state_type} state found for {user_id}")
                return False
                
            # Update context
            current_state.context.update(context_updates)
            
            # Calculate remaining TTL
            remaining_seconds = current_state.time_remaining_seconds()
            
            if remaining_seconds <= 0:
                self.logger.warning(f"⏰ State expired during update for {user_id}:{state_type}")
                await self.delete_user_state(user_id, state_type)
                return False
            
            # Save updated state with remaining TTL
            state_key = get_state_key(user_id, state_type)
            
            success = await self.state_cache.set(
                key=state_key,
                value=current_state.to_dict(),
                ttl=remaining_seconds
            )
            
            if success:
                self.logger.info(f"✅ Updated {state_type} state for {user_id}")
            else:
                self.logger.error(f"❌ Failed to update {state_type} state for {user_id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error updating state for {user_id}:{state_type}: {e}")
            return False
            
    async def delete_user_state(self, user_id: str, state_type: str) -> bool:
        """
        Delete user state for specified type.
        
        Args:
            user_id: User identifier  
            state_type: State type ("button" or "list")
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            state_key = get_state_key(user_id, state_type)
            
            success = await self.state_cache.delete(state_key)
            
            if success:
                self.logger.info(f"🗑️ Deleted {state_type} state for {user_id}")
            else:
                self.logger.debug(f"🔍 No {state_type} state found to delete for {user_id}")
                
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Error deleting state for {user_id}:{state_type}: {e}")
            return False
            
    async def delete_all_user_states(self, user_id: str) -> Dict[str, bool]:
        """
        Delete all states for user (button and list).
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with deletion results for each state type
        """
        results = {}
        
        try:
            # Delete button state
            results[STATE_TYPE_BUTTON] = await self.delete_user_state(user_id, STATE_TYPE_BUTTON)
            
            # Delete list state  
            results[STATE_TYPE_LIST] = await self.delete_user_state(user_id, STATE_TYPE_LIST)
            
            deleted_count = sum(1 for success in results.values() if success)
            self.logger.info(f"🧹 Cleaned up {deleted_count}/2 states for {user_id}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Error cleaning up all states for {user_id}: {e}")
            return results
            
    async def get_user_state_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Get summary of all user states.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with state summary information
        """
        try:
            summary = {
                "user_id": user_id,
                "states": {},
                "has_active_states": False,
                "checked_at": datetime.utcnow().isoformat() + 'Z'
            }
            
            # Check button state
            button_state = await self.get_user_state(user_id, STATE_TYPE_BUTTON)
            if button_state:
                summary["states"][STATE_TYPE_BUTTON] = {
                    "active": True,
                    "expires_in_seconds": button_state.time_remaining_seconds(),
                    "created_at": button_state.created_at,
                    "context_keys": list(button_state.context.keys())
                }
                summary["has_active_states"] = True
            else:
                summary["states"][STATE_TYPE_BUTTON] = {"active": False}
                
            # Check list state
            list_state = await self.get_user_state(user_id, STATE_TYPE_LIST)
            if list_state:
                summary["states"][STATE_TYPE_LIST] = {
                    "active": True,
                    "expires_in_seconds": list_state.time_remaining_seconds(),
                    "created_at": list_state.created_at,
                    "context_keys": list(list_state.context.keys())
                }
                summary["has_active_states"] = True
            else:
                summary["states"][STATE_TYPE_LIST] = {"active": False}
                
            return summary
            
        except Exception as e:
            self.logger.error(f"❌ Error getting state summary for {user_id}: {e}")
            return {
                "user_id": user_id,
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat() + 'Z'
            }
            
    async def cleanup_expired_states(self) -> Dict[str, int]:
        """
        Cleanup expired states (for maintenance).
        
        Note: Redis TTL should handle this automatically, but this
        provides a manual cleanup option for maintenance.
        
        Returns:
            Dictionary with cleanup statistics
        """
        try:
            # This is a placeholder for manual cleanup
            # Redis TTL handles automatic expiration
            self.logger.info("🧹 Expired state cleanup - Redis TTL handles automatic cleanup")
            
            return {
                "redis_ttl_active": True,
                "manual_cleanup_needed": False,
                "message": "Redis handles automatic state cleanup via TTL"
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error during state cleanup: {e}")
            return {
                "error": str(e),
                "cleanup_failed": True
            }