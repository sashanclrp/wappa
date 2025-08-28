"""
User Storage Logic

Handles user profile data storage and retrieval using Redis cache
with 24-hour TTL and comprehensive user metadata.
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from wappa.domain.interfaces.cache_interface import ICache

from ..constants import get_user_profile_key


async def store_user_data(webhook, user_id: str, user_cache: ICache,
                          metadata: Dict[str, Any], ttl_seconds: int) -> Dict[str, Any]:
    """
    Store or update user profile data in cache.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        user_cache: Redis user cache instance
        metadata: Extracted message metadata
        ttl_seconds: TTL for cached data (24 hours)
        
    Returns:
        Dictionary with storage result
    """
    try:
        # Get existing user data
        user_key = get_user_profile_key(user_id)
        existing_data = await user_cache.get(user_key)
        
        current_time = datetime.utcnow().isoformat() + 'Z'
        
        if existing_data:
            # Update existing user data
            if isinstance(existing_data, str):
                user_profile = json.loads(existing_data)
            else:
                user_profile = existing_data
                
            # Update counters and timestamps
            user_profile["message_count"] = user_profile.get("message_count", 0) + 1
            user_profile["last_seen"] = current_time
            user_profile["last_message_type"] = metadata.get("message_type", "unknown")
            
            # Update profile info if available
            if metadata.get("user_metadata"):
                user_meta = metadata["user_metadata"]
                if user_meta.get("profile_name"):
                    user_profile["profile_name"] = user_meta["profile_name"]
                if user_meta.get("display_name"):
                    user_profile["display_name"] = user_meta["display_name"]
                    
        else:
            # Create new user profile
            user_profile = {
                "user_id": user_id,
                "first_seen": current_time,
                "last_seen": current_time,
                "message_count": 1,
                "last_message_type": metadata.get("message_type", "unknown"),
                "created_by": "echo_project"
            }
            
            # Add profile info if available
            if metadata.get("user_metadata"):
                user_meta = metadata["user_metadata"]
                user_profile["profile_name"] = user_meta.get("profile_name")
                user_profile["display_name"] = user_meta.get("display_name")
                
        # Add platform context
        if metadata.get("platform_metadata"):
            platform_meta = metadata["platform_metadata"]
            user_profile["platform_context"] = {
                "tenant_key": platform_meta.get("tenant_key"),
                "phone_number_id": platform_meta.get("phone_number_id"),
                "business_account_id": platform_meta.get("business_account_id")
            }
            
        # Store updated profile with TTL
        success = await user_cache.set(
            key=user_key,
            value=user_profile,
            ttl=ttl_seconds
        )
        
        if success:
            return {
                "success": True,
                "action": "updated" if existing_data else "created",
                "user_profile": user_profile,
                "message_count": user_profile["message_count"],
                "ttl_seconds": ttl_seconds
            }
        else:
            return {
                "success": False,
                "error": "Failed to store user data in cache",
                "user_id": user_id
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id
        }


async def get_user_data(user_id: str, user_cache: ICache) -> Dict[str, Any]:
    """
    Retrieve user profile data from cache.
    
    Args:
        user_id: User identifier
        user_cache: Redis user cache instance
        
    Returns:
        Dictionary with user data or None if not found
    """
    try:
        user_key = get_user_profile_key(user_id)
        user_data = await user_cache.get(user_key)
        
        if not user_data:
            return {
                "found": False,
                "user_id": user_id,
                "reason": "No cached data found"
            }
            
        # Parse data if it's JSON string
        if isinstance(user_data, str):
            user_profile = json.loads(user_data)
        else:
            user_profile = user_data
            
        return {
            "found": True,
            "user_profile": user_profile,
            "message_count": user_profile.get("message_count", 0),
            "first_seen": user_profile.get("first_seen"),
            "last_seen": user_profile.get("last_seen"),
            "last_message_type": user_profile.get("last_message_type")
        }
        
    except Exception as e:
        return {
            "found": False,
            "error": str(e),
            "user_id": user_id
        }